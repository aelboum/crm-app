import { describe, expect, it } from "vitest";

import { embedSnippet, escapeHtml, type SnippetForm } from "./embedSnippet";

/*
 * The embed code for external websites (decision P12-W): labels are
 * escaped, the script holds no markup a label could close, and the request
 * carries the honeypot, the consent, attribution and an Idempotency-Key.
 */

const FORM: SnippetForm = {
  key: "contact-us",
  name: "Contact us",
  fields: [
    { key: "first_name", label: "First name", type: "text", required: true },
    { key: "email", label: 'E-mail "work"', type: "email", required: true },
    {
      key: "topic",
      label: "Topic",
      type: "select",
      required: false,
      options: ["<b>Sales</b>"],
    },
    {
      key: "notes",
      label: "</script><script>alert(1)</script>",
      type: "textarea",
      required: false,
    },
  ],
  consent_text: "Yes, email me & my team",
  thank_you: "Thanks!",
};

const WS = "11111111-2222-4333-8444-555555555555";

describe("embed snippet", () => {
  const code = embedSnippet(FORM, "https://app.example.com", WS);

  it("posts to the workspace's public form endpoint", () => {
    expect(code).toContain(
      `"https://app.example.com/v1/public/forms/${WS}/contact-us"`,
    );
    expect(code).toContain('"Idempotency-Key": key');
    expect(code).toContain("attribution: attribution");
    expect(code).toContain("utm_source");
  });

  it("escapes every label, option and the consent text", () => {
    expect(code).toContain("E-mail &quot;work&quot;");
    expect(code).toContain("&lt;b&gt;Sales&lt;/b&gt;");
    expect(code).toContain("Yes, email me &amp; my team");
    expect(code).not.toContain("<script>alert(1)");
    expect(code.match(/<\/script>/g)).toHaveLength(1);
  });

  it("includes the hidden honeypot and the consent box", () => {
    expect(code).toContain('name="website" tabindex="-1"');
    expect(code).toContain('name="__consent"');
    const plain = embedSnippet(
      { ...FORM, consent_text: null },
      "https://app.example.com",
      WS,
    );
    expect(plain).not.toContain('name="__consent"');
  });

  it("escapes HTML special characters", () => {
    expect(escapeHtml(`<a href="x">&'</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;",
    );
  });
});
