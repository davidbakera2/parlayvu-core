/**
 * ParlayVU contact handler — Resend only.
 * Pages env: RESEND_API_KEY (secret). Vars: CONTACT_* from wrangler.toml or dashboard.
 */

const MAX_NAME = 120;
const MAX_EMAIL = 254;
const MAX_MESSAGE = 8000;

export async function onRequestPost({ request, env }) {
  if (request.method !== "POST") {
    return json({ error: "Method not allowed" }, 405);
  }

  const apiKey = env.RESEND_API_KEY || env.RESEND_API;
  if (!apiKey) {
    console.error("RESEND_API_KEY or RESEND_API is not configured on Pages");
    return json({ error: "Contact form is not configured." }, 503);
  }

  const toEmail = env.CONTACT_TO_EMAIL;
  const fromEmail = env.CONTACT_FROM_EMAIL;
  const fromName = env.CONTACT_FROM_NAME || "Website";

  if (!toEmail || !fromEmail) {
    console.error("Missing CONTACT_TO_EMAIL or CONTACT_FROM_EMAIL");
    return json({ error: "Contact form is not configured." }, 503);
  }

  let name = "";
  let email = "";
  let message = "";
  let honeypot = "";

  const contentType = request.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = await request.json();
    name = String(body.name ?? "").trim();
    email = String(body.email ?? "").trim();
    message = String(body.message ?? "").trim();
    honeypot = String(body.website ?? "").trim();
  } else {
    const form = await request.formData();
    name = String(form.get("name") ?? "").trim();
    email = String(form.get("email") ?? "").trim();
    message = String(form.get("message") ?? "").trim();
    honeypot = String(form.get("website") ?? "").trim();
  }

  if (honeypot) {
    return json({ ok: true });
  }

  const validationError = validateContact({ name, email, message });
  if (validationError) {
    return json({ error: validationError }, 400);
  }

  const subject = `Website contact from ${name}`;
  const bodyText = `Name: ${name}\nEmail: ${email}\n\n${message}`;

  try {
    await sendViaResend(apiKey, {
      fromEmail,
      fromName,
      toEmail,
      replyEmail: email,
      replyName: name,
      subject,
      bodyText,
    });
    return json({ ok: true });
  } catch (err) {
    console.error("Resend delivery failed", err);
    return json(
      {
        error:
          "We could not send your message right now. Please try again in a few minutes.",
      },
      502,
    );
  }
}

function validateContact({ name, email, message }) {
  if (!name || !email || !message) {
    return "Name, email, and message are required.";
  }
  if (name.length > MAX_NAME) return "Name is too long.";
  if (email.length > MAX_EMAIL || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return "Invalid email address.";
  }
  if (message.length > MAX_MESSAGE) return "Message is too long.";
  return null;
}

async function sendViaResend(
  apiKey,
  { fromEmail, fromName, toEmail, replyEmail, replyName, subject, bodyText },
) {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: `${fromName} <${fromEmail}>`,
      to: [toEmail],
      reply_to: `${replyName} <${replyEmail}>`,
      subject,
      text: bodyText,
    }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.message ?? data.error ?? res.statusText;
    throw new Error(`Resend ${res.status}: ${detail}`);
  }
}

function json(body, status = 200) {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}
