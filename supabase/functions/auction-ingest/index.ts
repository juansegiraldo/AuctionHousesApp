// Puerta de entrada del pipeline a los esquemas auction / auction_des.
// El esquema no esta expuesto en la Data API; esta funcion es el unico acceso.
// Autenticacion propia: cabecera x-ingest-token, cuyo sha256 vive en
// <esquema>.ingest_tokens. Por eso se despliega con verify_jwt = false.
import postgres from "npm:postgres@3.4.5";
import { createClient } from "npm:@supabase/supabase-js@2";

const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, { prepare: false, max: 2 });
const SCHEMAS = new Set(["auction", "auction_des"]);
const BUCKET = "auction-archive";

// Ojo con los parametros JSON: van como `${JSON.stringify(x)}::text::jsonb`.
// Con `::jsonb` a secas postgres.js vuelve a serializar la cadena y Postgres
// recibe un string JSON, no un array ("cannot call jsonb_to_recordset on a non-array").
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function readBody(req: Request) {
  // El cliente comprime: un lote de 500 lotes pesa ~1 MB sin comprimir.
  const stream = req.headers.get("x-gzip") === "1"
    ? req.body!.pipeThrough(new DecompressionStream("gzip"))
    : req.body!;
  return JSON.parse(await new Response(stream).text());
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "solo POST" }, 405);
  const schema = req.headers.get("x-schema") ?? "";
  if (!SCHEMAS.has(schema)) return json({ error: "esquema no permitido" }, 400);
  const s = sql(schema);

  const token = req.headers.get("x-ingest-token") ?? "";
  const ok = await sql`select 1 from ${s}.ingest_tokens where token_sha256 = ${await sha256(token)}`;
  if (!token || ok.length === 0) return json({ error: "token invalido" }, 401);

  try {
    const b = await readBody(req);
    switch (b.op) {
      case "run_start": {
        const [r] = await sql`insert into ${s}.runs (git_sha) values (${b.git_sha ?? null}) returning run_id`;
        return json({ run_id: Number(r.run_id) });
      }
      case "run_finish": {
        await sql`update ${s}.runs set finished_at = now(), status = ${b.status},
          stage_failed = ${b.stage_failed ?? null}, counts = ${JSON.stringify(b.counts ?? {})}::text::jsonb
          where run_id = ${b.run_id}`;
        return json({ ok: true });
      }
      case "raw": {
        const res = await sql`
          insert into ${s}.raw_lots (house_slug, lot_url, content_hash, payload, source_file, first_run_id)
          select house_slug, lot_url, content_hash, payload, source_file, ${b.run_id ?? null}::bigint
          from jsonb_to_recordset(${JSON.stringify(b.rows)}::text::jsonb)
            as t(house_slug text, lot_url text, content_hash text, payload jsonb, source_file text)
          on conflict do nothing`;
        return json({ inserted: res.count });
      }
      case "missing": {
        // De los hashes que el cliente tiene, cuales no estan aun en la base:
        // asi una corrida normal envia solo lo nuevo y no las ~92.000 versiones.
        const rows = await sql`
          select t.h from jsonb_array_elements_text(${JSON.stringify(b.hashes)}::text::jsonb) as t(h)
          where not exists (
            select 1 from ${s}.raw_lots r
            where r.house_slug = ${b.house_slug} and r.content_hash = t.h)`;
        return json({ missing: rows.map((r) => r.h) });
      }
      case "degraded": {
        // Versiones cargadas en esta corrida que traen MENOS campos con valor que
        // la version anterior del mismo lote: la huella de un re-scrape en el que
        // fallo la pagina de detalle y solo quedo el catalogo.
        const rows = await sql`
          with nuevo as (
            select house_slug, lot_url, payload from ${s}.raw_lots
            where first_run_id = ${b.run_id}::bigint),
          previo as (
            select distinct on (r.house_slug, r.lot_url) r.house_slug, r.lot_url, r.payload
            from ${s}.raw_lots r join nuevo n using (house_slug, lot_url)
            where r.first_run_id is distinct from ${b.run_id}::bigint
            order by r.house_slug, r.lot_url, r.ingested_at desc)
          select n.house_slug, count(*)::int as con_previa,
            (count(*) filter (where
              (select count(*) from jsonb_each(n.payload) e where e.value <> 'null'::jsonb) <
              (select count(*) from jsonb_each(p.payload) e where e.value <> 'null'::jsonb)))::int as degraded
          from nuevo n join previo p using (house_slug, lot_url)
          group by 1`;
        return json({ houses: rows });
      }
      case "rejects": {
        await sql`
          insert into ${s}.rejects (run_id, house_slug, source_file, motivo, n)
          select ${b.run_id ?? null}::bigint, house_slug, source_file, motivo, n
          from jsonb_to_recordset(${JSON.stringify(b.rows)}::text::jsonb)
            as t(house_slug text, source_file text, motivo text, n integer)`;
        return json({ ok: true });
      }
      case "stats": {
        const rows = await sql`
          select house_slug, count(*)::int as versions, count(distinct lot_url)::int as lots
          from ${s}.raw_lots group by 1 order by 1`;
        const [size] = await sql`select pg_database_size(current_database())::bigint as bytes`;
        return json({ houses: rows, db_bytes: Number(size.bytes) });
      }
      case "export": {
        // Paginacion por clave: after = [lot_url, content_hash] de la ultima fila.
        const [u, h] = b.after ?? ["", ""];
        const rows = await sql`
          select lot_url, content_hash, payload, source_file, ingested_at
          from ${s}.raw_lots
          where house_slug = ${b.house_slug} and (lot_url, content_hash) > (${u}, ${h})
          order by lot_url, content_hash limit ${Math.min(b.limit ?? 500, 1000)}`;
        return json({ rows });
      }
      case "sign_upload": {
        const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
        const { data, error } = await sb.storage.from(BUCKET).createSignedUploadUrl(b.path, { upsert: true });
        if (error) return json({ error: error.message }, 500);
        return json({ signed_url: data.signedUrl });
      }
      default:
        return json({ error: `op desconocida: ${b.op}` }, 400);
    }
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
});
