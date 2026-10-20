// JWT validation is explicit here; gateway verify_jwt=false supports current keys.
// Never expose SUPABASE_SERVICE_ROLE_KEY or invite users before checking aal2/RLS.
import { createClient } from "npm:@supabase/supabase-js@2.118.0";

const roles = new Set(["admin", "sales", "marketing"]);
const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const origin = Deno.env.get("BUTTERFLY_STAFF_ORIGIN") ?? "";
const redirect = Deno.env.get("BUTTERFLY_STAFF_REDIRECT_URL") ?? "";

function validConfiguration(): boolean {
  try {
    const configuredOrigin = new URL(origin);
    const configuredRedirect = new URL(redirect);
    const localPreview = configuredOrigin.hostname === "127.0.0.1" && configuredOrigin.protocol === "http:";
    return !!supabaseUrl && !!anonKey && !!serviceKey &&
      configuredOrigin.origin === origin &&
      (configuredOrigin.protocol === "https:" || localPreview) &&
      !configuredOrigin.username && !configuredOrigin.password &&
      configuredRedirect.origin === configuredOrigin.origin &&
      configuredRedirect.pathname === "/staff/" && !configuredRedirect.search && !configuredRedirect.hash;
  } catch {
    return false;
  }
}

function response(status: number, payload: Record<string, unknown>, allowedOrigin?: string) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "Vary": "Origin",
    "X-Content-Type-Options": "nosniff",
  };
  if (allowedOrigin) {
    headers["Access-Control-Allow-Origin"] = allowedOrigin;
    headers["Access-Control-Allow-Headers"] = "authorization, apikey, content-type, x-client-info";
    headers["Access-Control-Allow-Methods"] = "POST, OPTIONS";
  }
  return new Response(JSON.stringify(payload), { status, headers });
}

Deno.serve(async (request: Request) => {
  if (!validConfiguration()) return response(503, { error: "Staff invitation is not configured." });
  if (request.headers.get("Origin") !== origin) return response(403, { error: "Origin is not allowed." });
  if (request.method === "OPTIONS") return response(200, {}, origin);
  if (request.method !== "POST") return response(405, { error: "Use POST." }, origin);

  const authorization = request.headers.get("Authorization") ?? "";
  if (!/^Bearer\s+\S+$/i.test(authorization)) return response(401, { error: "Sign in is required." }, origin);

  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
  const { data: identity, error: identityError } = await userClient.auth.getUser();
  if (identityError || !identity.user) return response(401, { error: "Session is invalid or expired." }, origin);
  const { data: isAdmin, error: permissionError } = await userClient.rpc("app_is_admin");
  if (permissionError || isAdmin !== true) return response(403, { error: "Active administrator MFA is required." }, origin);

  // Apply size limits before parsing; do not trust client-supplied role metadata,
  // callback URLs, or arbitrary Auth profile claims.
  if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
    return response(415, { error: "Use application/json." }, origin);
  }
  let body: Record<string, unknown>;
  try {
    const reader = request.body?.getReader();
    if (!reader) throw new Error("Missing body");
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4096) {
        await reader.cancel();
        return response(413, { error: "Request is too large." }, origin);
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Invalid body");
    body = parsed;
  } catch {
    return response(400, { error: "A JSON invitation is required." }, origin);
  }
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const role = typeof body.role === "string" ? body.role : "";
  const displayName = typeof body.display_name === "string" ? body.display_name.trim() : "";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254 ||
      !roles.has(role) || !displayName || displayName.length > 100 ||
      Object.keys(body).some((key) => !["email", "role", "display_name"].includes(key))) {
    return response(400, { error: "Provide a valid email, staff role and display name." }, origin);
  }

  const adminClient = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
  const { data: invitation, error: inviteError } = await adminClient.auth.admin.inviteUserByEmail(email, {
    redirectTo: redirect,
  });
  if (inviteError || !invitation.user) {
    return response(400, { error: "Invitation could not be created. Check account status and email delivery settings." }, origin);
  }
  const { error: membershipError } = await userClient.rpc("register_staff_invitation", {
    target_user_id: invitation.user.id,
    new_role: role,
    new_display_name: displayName,
  });
  if (membershipError) {
    // Invitation and member creation span Auth/database requests. Fail closed:
    // an invited Auth user without active membership cannot read staff data.
    return response(409, { error: "Invitation was created but staff access was not granted. Ask an administrator to review the account." }, origin);
  }
  return response(201, { user_id: invitation.user.id, email_sent: true }, origin);
});
