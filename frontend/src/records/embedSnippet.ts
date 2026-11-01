/*
 * The code a workspace pastes into a website outside LeadStack (decision
 * P12-W): a plain HTML form and a small script that posts it to the public
 * form API, with an Idempotency-Key, the honeypot field, the consent box
 * when the form asks for consent, and the page's UTM parameters, address
 * and referrer as attribution. It works in any site builder that accepts
 * custom HTML (WordPress, Shopify, Webflow, Wix, plain sites). The site's
 * origin must be listed under Websites, or the browser's request is
 * refused. Every label and value is escaped; nothing from the page is
 * inserted as HTML.
 */

export interface SnippetField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  options?: string[] | null;
}

export interface SnippetForm {
  key: string;
  name: string;
  fields: SnippetField[];
  consent_text: string | null;
  thank_you: string;
}

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) => ESCAPES[c] ?? c);
}

const INPUT_TYPES: Record<string, string> = {
  email: "email",
  phone: "tel",
  number: "number",
  date: "date",
};

function fieldHtml(field: SnippetField, id: string): string {
  const name = escapeHtml(field.key);
  const label = escapeHtml(field.label);
  const required = field.required ? " required" : "";
  const fieldId = `${id}-${name}`;
  if (field.type === "textarea") {
    return `  <label for="${fieldId}">${label}</label>\n  <textarea id="${fieldId}" name="${name}"${required}></textarea>`;
  }
  if (field.type === "select") {
    const options = (field.options ?? [])
      .map((o) => `<option>${escapeHtml(o)}</option>`)
      .join("");
    return `  <label for="${fieldId}">${label}</label>\n  <select id="${fieldId}" name="${name}"${required}><option value=""></option>${options}</select>`;
  }
  if (field.type === "checkbox") {
    return `  <label><input type="checkbox" name="${name}"${required}> ${label}</label>`;
  }
  const type = INPUT_TYPES[field.type] ?? "text";
  return `  <label for="${fieldId}">${label}</label>\n  <input id="${fieldId}" type="${type}" name="${name}"${required}>`;
}

/** A JSON value safe to place inside a <script> element. */
function scriptJson(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026");
}

/** The HTML and script to paste into an external site. */
export function embedSnippet(
  form: SnippetForm,
  apiOrigin: string,
  workspaceId: string,
): string {
  const id = `leadstack-${form.key}`;
  const endpoint = `${apiOrigin}/v1/public/forms/${encodeURIComponent(workspaceId)}/${encodeURIComponent(form.key)}`;
  const consent = form.consent_text
    ? `\n  <label><input type="checkbox" name="__consent"> ${escapeHtml(form.consent_text)}</label>`
    : "";
  const fields = form.fields.map((f) => fieldHtml(f, id)).join("\n");
  const keys = scriptJson(
    form.fields.map((f) => ({ key: f.key, checkbox: f.type === "checkbox" })),
  );
  return `<form id="${escapeHtml(id)}" novalidate>
${fields}${consent}
  <div style="position:absolute;left:-10000px" aria-hidden="true"><input name="website" tabindex="-1" autocomplete="off"></div>
  <button type="submit">Send</button>
  <p role="status" aria-live="polite"></p>
</form>
<script>
(function () {
  var form = document.getElementById(${scriptJson(id)});
  var fields = ${keys};
  var status = form.querySelector("[role=status]");
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!form.reportValidity()) return;
    var answers = {};
    fields.forEach(function (f) {
      var input = form.elements[f.key];
      answers[f.key] = f.checkbox ? input.checked : (input.value || null);
    });
    var params = new URLSearchParams(window.location.search);
    var attribution = { page_url: window.location.href, referrer: document.referrer || null };
    ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"].forEach(function (k) {
      if (params.get(k)) attribution[k] = params.get(k);
    });
    var consent = form.elements.__consent;
    var key = Array.from(crypto.getRandomValues(new Uint8Array(16)), function (b) {
      return b.toString(16).padStart(2, "0");
    }).join("");
    form.querySelector("button").disabled = true;
    fetch(${scriptJson(endpoint)}, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({
        answers: answers,
        consent: consent ? consent.checked : false,
        website: form.elements.website.value,
        attribution: attribution
      })
    }).then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).then(function (result) {
      form.reset();
      status.textContent = result.thank_you;
    }).catch(function () {
      status.textContent = "Sorry, that did not work. Please try again.";
    }).finally(function () {
      form.querySelector("button").disabled = false;
    });
  });
})();
</script>`;
}
