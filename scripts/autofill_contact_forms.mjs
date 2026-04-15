#!/usr/bin/env node
import fs from 'node:fs/promises';
import readline from 'node:readline/promises';
import { stdin as input, stdout as output, exit } from 'node:process';
import puppeteer from 'puppeteer';

function parseArgs(argv) {
  const args = {
    input: '',
    apiBaseUrl: process.env.AUTOFILL_API_BASE_URL || 'http://127.0.0.1:8000',
    limit: 10,
    headless: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === '--input' && next) {
      args.input = next;
      i += 1;
    } else if (arg === '--api-base-url' && next) {
      args.apiBaseUrl = next;
      i += 1;
    } else if (arg === '--limit' && next) {
      args.limit = Math.max(1, Number(next) || 10);
      i += 1;
    } else if (arg === '--headless') {
      args.headless = true;
    } else if (arg === '--help' || arg === '-h') {
      printHelp();
      exit(0);
    }
  }

  return args;
}

function printHelp() {
  console.log(`\nMap to List - Puppeteer 自動入力\n\n使い方:\n  npm run autofill-forms -- --input ./contact-form-autofill.json\n  npm run autofill-forms -- --api-base-url http://127.0.0.1:8000 --limit 5\n\nオプション:\n  --input <file>         JSONファイルから問い合わせフォームURLと入力設定を読み込む\n  --api-base-url <url>   APIから自動入力データを取得する\n  --limit <n>            対象件数の上限 (既定: 10)\n  --headless             画面を表示せず実行する（通常は使わない）\n`);
}

function renderTemplate(template, varsMap = {}) {
  let out = String(template || '');
  for (const [key, value] of Object.entries(varsMap)) {
    out = out.replaceAll(`{{${key}}}`, String(value || ''));
  }
  return out;
}

async function loadPayload(args) {
  if (args.input) {
    const raw = await fs.readFile(args.input, 'utf-8');
    return JSON.parse(raw);
  }

  const apiBaseUrl = String(args.apiBaseUrl || '').replace(/\/$/, '');
  const res = await fetch(`${apiBaseUrl}/api/contact-forms/autofill-data?limit=${args.limit}`);
  if (!res.ok) {
    throw new Error(`APIから自動入力データを取得できませんでした: HTTP ${res.status}`);
  }
  return res.json();
}

async function autofillPage(page, item, settings) {
  const varsMap = {
    sender_company: settings.sender_company || '',
    sender_name: settings.sender_name || '',
    sender_email: settings.sender_email || '',
    sender_phone: settings.sender_phone || '',
    target_company_name: item.lead_name || '',
    target_website: item.website || '',
    form_url: item.form_url || '',
  };

  const fillData = {
    sender_company: renderTemplate(settings.sender_company || '', varsMap).trim(),
    sender_name: renderTemplate(settings.sender_name || '', varsMap).trim(),
    sender_email: renderTemplate(settings.sender_email || '', varsMap).trim(),
    sender_phone: renderTemplate(settings.sender_phone || '', varsMap).trim(),
    subject: renderTemplate(settings.subject || '', varsMap).trim(),
    body: renderTemplate(settings.body || '', varsMap).trim(),
  };

  return page.evaluate((payload) => {
    const FIELD_RULES = [
      ['sender_company', /(company|organization|corporate|business|法人|会社|企業|屋号|貴社名|組織)/i],
      ['sender_name', /(full.?name|your.?name|name|担当者|氏名|お名前|ご担当者)/i],
      ['sender_email', /(e-?mail|email|mail|メール)/i],
      ['sender_phone', /(phone|tel|telephone|mobile|電話|携帯)/i],
      ['subject', /(subject|title|件名|題名)/i],
      ['body', /(message|inquiry|contact|body|content|detail|comment|お問い合わせ内容|本文|ご相談|相談内容|備考)/i],
    ];

    function isVisible(el) {
      if (!el || el.disabled) return false;
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }

    function labelText(el) {
      const texts = [];
      if (el.labels) {
        texts.push(...Array.from(el.labels).map((x) => x.textContent || ''));
      }
      const id = el.getAttribute('id');
      if (id) {
        const byFor = document.querySelector(`label[for="${id}"]`);
        if (byFor) texts.push(byFor.textContent || '');
      }
      const closest = el.closest('label');
      if (closest) texts.push(closest.textContent || '');
      return texts.join(' ');
    }

    function descriptor(el) {
      return [
        el.getAttribute('name') || '',
        el.getAttribute('id') || '',
        el.getAttribute('placeholder') || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('autocomplete') || '',
        el.className || '',
        labelText(el),
      ].join(' ').toLowerCase();
    }

    function dispatch(el) {
      ['input', 'change', 'blur'].forEach((type) => {
        el.dispatchEvent(new Event(type, { bubbles: true }));
      });
    }

    function setValue(el, value) {
      if (!value) return false;
      const tag = (el.tagName || '').toLowerCase();
      if (tag === 'select') {
        const options = Array.from(el.options || []);
        const normalizedValue = String(value).trim().toLowerCase();
        const found = options.find((option) => String(option.textContent || '').trim().toLowerCase() === normalizedValue);
        if (found) {
          el.value = found.value;
          dispatch(el);
          return true;
        }
        return false;
      }
      el.focus();
      el.value = value;
      el.style.outline = '2px solid #5e8fcf';
      el.style.backgroundColor = '#eef6ff';
      dispatch(el);
      return true;
    }

    const controls = Array.from(document.querySelectorAll('input, textarea, select')).filter((el) => {
      if (!isVisible(el)) return false;
      const type = String(el.getAttribute('type') || '').toLowerCase();
      return !['hidden', 'submit', 'button', 'reset', 'radio', 'checkbox', 'file', 'password', 'search'].includes(type);
    });

    const used = new Set();
    const filled = [];
    const missed = [];

    for (const [key, pattern] of FIELD_RULES) {
      const value = String(payload[key] || '').trim();
      if (!value) continue;

      const ranked = controls
        .filter((el) => !used.has(el))
        .map((el) => {
          const text = descriptor(el);
          let score = pattern.test(text) ? 50 : 0;
          const type = String(el.getAttribute('type') || '').toLowerCase();
          const tag = (el.tagName || '').toLowerCase();
          if (key === 'sender_email' && type === 'email') score += 20;
          if (key === 'sender_phone' && (type === 'tel' || /tel|phone/.test(text))) score += 20;
          if (key === 'body' && tag === 'textarea') score += 25;
          if (key === 'subject' && tag === 'input') score += 15;
          if (String(el.value || '').trim()) score -= 5;
          return { el, score };
        })
        .sort((a, b) => b.score - a.score);

      const best = ranked[0];
      if (best && best.score > 0 && setValue(best.el, value)) {
        used.add(best.el);
        filled.push(key);
      } else {
        missed.push(key);
      }
    }

    return {
      title: document.title || '',
      filled,
      missed,
    };
  }, fillData);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const payload = await loadPayload(args);
  const items = Array.isArray(payload.items) ? payload.items.slice(0, args.limit) : [];
  const settings = payload.settings || {};

  if (!items.length) {
    throw new Error('自動入力の対象フォームURLがありません。先に問い合わせフォームURLを取得してください。');
  }

  const browser = await puppeteer.launch({
    headless: args.headless,
    defaultViewport: null,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  console.log(`\n${items.length}件のフォームに対して自動入力を開始します。送信は手動です。\n`);

  for (const item of items) {
    const page = await browser.newPage();
    await page.goto(item.form_url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await new Promise((resolve) => setTimeout(resolve, 1500));

    const result = await autofillPage(page, item, settings);
    console.log(`- ${item.lead_name || item.form_url}`);
    console.log(`  URL: ${item.form_url}`);
    console.log(`  入力済み: ${result.filled.join(', ') || 'なし'}`);
    if (result.missed.length) {
      console.log(`  未入力: ${result.missed.join(', ')}`);
    }
  }

  console.log('\nブラウザは開いたままです。内容を確認して、必要なら手修正して送信してください。');
  const rl = readline.createInterface({ input, output });
  await rl.question('終了する場合は Enter を押してください: ');
  rl.close();
  await browser.close();
}

main().catch((err) => {
  console.error(`\n[autofill-forms] ${err instanceof Error ? err.message : String(err)}`);
  exit(1);
});
