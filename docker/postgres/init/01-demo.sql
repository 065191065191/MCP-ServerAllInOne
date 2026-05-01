CREATE TABLE IF NOT EXISTS demo_ping (
  id bigserial PRIMARY KEY,
  msg text NOT NULL DEFAULT 'hello from docker postgres',
  created_at timestamptz NOT NULL DEFAULT now()
);
