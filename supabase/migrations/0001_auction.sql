-- Registro duradero de lo scrapeado. Se aplica dos veces: tal cual (esquema
-- `auction`) y con el nombre cambiado a `auction_des` para probar cargas.
-- El esquema NO se expone en la Data API: solo entra la funcion auction-ingest.

create schema if not exists auction;
revoke all on schema auction from anon, authenticated;

-- Una fila por corrida del pipeline: que se cargo, cuando y con que codigo.
create table auction.runs (
  run_id       bigint generated always as identity primary key,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  git_sha      text,
  status       text not null default 'running',
  stage_failed text,
  counts       jsonb
);

-- Cada version distinta de cada lote, tal como salio del scraper.
-- content_hash = sha256 del registro sin scraped_at: re-scrapear lo mismo
-- no crea una version nueva.
create table auction.raw_lots (
  house_slug   text not null,
  lot_url      text not null,
  content_hash text not null,
  payload      jsonb not null,
  source_file  text,
  ingested_at  timestamptz not null default now(),
  first_run_id bigint references auction.runs,
  primary key (house_slug, lot_url, content_hash)
);

-- Lo que se descarto y por que (fichero de prueba, linea rota, sin lot_url).
create table auction.rejects (
  run_id      bigint references auction.runs,
  house_slug  text,
  source_file text,
  motivo      text not null,
  n           integer not null
);

-- Solo el sha256 del token de carga; el token vive en el .env local.
create table auction.ingest_tokens (
  token_sha256 text primary key,
  created_at   timestamptz not null default now()
);

-- raw_lots es solo de insercion: nada del pipeline puede borrar ni pisar.
create function auction.forbid_change() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception 'auction.raw_lots es solo de insercion (% rechazado)', tg_op;
end $$;

create trigger raw_lots_append_only before update or delete on auction.raw_lots
  for each row execute function auction.forbid_change();
create trigger raw_lots_no_truncate before truncate on auction.raw_lots
  for each statement execute function auction.forbid_change();

alter table auction.runs          enable row level security;
alter table auction.raw_lots      enable row level security;
alter table auction.rejects       enable row level security;
alter table auction.ingest_tokens enable row level security;
