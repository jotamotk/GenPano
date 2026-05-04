-- Module C-1: Products (SKU-level scoping for generation)
--
-- A Product is a stable research subject (lifetime: months) that belongs to a
-- Brand. Topics may optionally pin to a specific Product so that downstream
-- Prompts and Queries inherit SKU-level focus.
--
-- Insertion layer is Topic; Prompt and Query inherit via FK chain
-- (no independent product_id on prompt/query — keeps the layer hierarchy
-- consistent: a topic owns its product attribution).

CREATE TABLE IF NOT EXISTS products (
    id            SERIAL PRIMARY KEY,
    brand_id      INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    name          VARCHAR(256) NOT NULL,
    sku           VARCHAR(128),
    category      VARCHAR(128),
    description   TEXT,
    aliases       JSONB,
    status        VARCHAR(16) NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'archived')),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_brand        ON products (brand_id);
CREATE INDEX IF NOT EXISTS idx_products_status_brand ON products (status, brand_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_products_brand_name
    ON products (brand_id, name);

-- Primary insertion point: a Topic may belong to a single Product.
-- ON DELETE SET NULL so deleting a product doesn't orphan topics.
ALTER TABLE topics ADD COLUMN IF NOT EXISTS product_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_topics_product ON topics (product_id);
