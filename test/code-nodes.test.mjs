// Unit tests for the JavaScript inside the workflows' Code nodes.
// Runs each node's jsCode with stubbed n8n globals ($input, $json, $()).
// Usage: node --test test/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const load = (file) => JSON.parse(readFileSync(new URL(`../workflows/${file}`, import.meta.url)));

function runCode(workflow, nodeName, { items = [], refs = {} }) {
  const node = workflow.nodes.find((n) => n.name === nodeName);
  assert.ok(node, `node ${nodeName} not found`);
  const $input = { all: () => items, first: () => items[0] };
  const $ = (name) => ({ all: () => refs[name], first: () => refs[name][0] });
  const fn = new Function('$input', '$', '$json', node.parameters.jsCode);
  return fn($input, $, items[0]?.json);
}

const aiReply = (obj) => ({ json: { choices: [{ message: { content: JSON.stringify(obj) } }] } });

test('invoice: consistent totals pass validation', () => {
  const wf = load('03-ai-invoice-extractor.json');
  const [out] = runCode(wf, 'Validate Totals', {
    items: [aiReply({ vendor: 'AWS', total: 110, subtotal: 100, tax: 10, line_items: [{ amount: 60 }, { amount: 40 }] })],
    refs: { 'Invoice Email Arrives': [{ json: { subject: 'Invoice', from: { value: [{ address: 'billing@aws.com' }] } } }] },
  });
  assert.equal(out.json.needs_review, false);
  assert.equal(out.json.email_from, 'billing@aws.com');
});

test('invoice: mismatched totals are flagged for review', () => {
  const wf = load('03-ai-invoice-extractor.json');
  const [out] = runCode(wf, 'Validate Totals', {
    items: [aiReply({ vendor: 'X', total: 150, subtotal: 100, tax: 10, line_items: [{ amount: 90 }] })],
    refs: { 'Invoice Email Arrives': [{ json: {} }] },
  });
  assert.equal(out.json.needs_review, true);
  assert.match(out.json.issues, /subtotal \+ tax != total/);
  assert.match(out.json.issues, /line items != subtotal/);
});

test('invoice: unparseable AI output is flagged, not crashed', () => {
  const wf = load('03-ai-invoice-extractor.json');
  const [out] = runCode(wf, 'Validate Totals', {
    items: [{ json: { choices: [{ message: { content: 'not json' } }] } }],
    refs: { 'Invoice Email Arrives': [{ json: {} }] },
  });
  assert.equal(out.json.needs_review, true);
  assert.match(out.json.issues, /missing total/);
});

test('email triage: unknown categories fall back to "other"', () => {
  const wf = load('01-ai-email-triage.json');
  const email = { json: { messageId: 'm1', subject: 'Hi', from: 'a@b.co' } };
  const out = runCode(wf, 'Parse AI Result', {
    items: [aiReply({ category: 'weird', urgency: 'high', summary: 's', needs_reply: true, draft_reply: 'ok' })],
    refs: { 'Clean Email': [email] },
  });
  assert.equal(out[0].json.category, 'other');
  assert.equal(out[0].json.subject, 'Hi');
});

test('email triage: body is trimmed and whitespace collapsed', () => {
  const wf = load('01-ai-email-triage.json');
  const out = runCode(wf, 'Clean Email', {
    items: [{ json: { id: '1', threadId: 't', subject: 'S', text: 'a\n\n   b  ' + 'x'.repeat(5000), from: { value: [{ address: 'p@q.co', name: 'P' }] } } }],
  });
  assert.ok(out[0].json.body.startsWith('a b '));
  assert.equal(out[0].json.body.length, 4000);
  assert.equal(out[0].json.from, 'p@q.co');
});

test('lead qualifier: free email domains are not business emails', () => {
  const wf = load('02-ai-lead-qualifier.json');
  const [gmail] = runCode(wf, 'Validate & Normalise', { items: [{ json: { body: { email: 'Bob@Gmail.com' } } }] });
  const [biz] = runCode(wf, 'Validate & Normalise', { items: [{ json: { body: { email: 'jane@acme.io' } } }] });
  assert.equal(gmail.json.valid, true);
  assert.equal(gmail.json.businessEmail, false);
  assert.equal(gmail.json.email, 'bob@gmail.com');
  assert.equal(biz.json.businessEmail, true);
});

test('lead qualifier: score is clamped and tier derived when AI returns junk', () => {
  const wf = load('02-ai-lead-qualifier.json');
  const [out] = runCode(wf, 'Parse Score', {
    items: [aiReply({ score: 250, tier: 'ultra' })],
    refs: { 'Validate & Normalise': [{ json: { email: 'a@b.co' } }] },
  });
  assert.equal(out.json.score, 100);
  assert.equal(out.json.tier, 'hot');
});
