-- Initial auction houses data based on research
-- This populates the auction_houses table with the researched houses

INSERT INTO auction_houses (name, country, website, description, scraping_config) VALUES

-- Colombian Houses
('Bogotá Auctions', 'Colombia', 'https://www.bogotaauctions.com', 
 'Casa de subastas colombiana especializada en arte latinoamericano, libros, grabados y objetos de colección. Opera tanto de forma presencial como en línea.',
 '{
   "strategy": "html_static",
   "frequency": "daily",
   "urls": {
     "active": "https://www.bogotaauctions.com/es/subastas-activas",
     "historical": "https://www.bogotaauctions.com/es/subastas-historicas"
   },
   "selectors": {
     "auction_links": "a.titulo-subasta",
     "lots": "div.lote"
   }
 }'::jsonb),

('Lefebre Subastas', 'Colombia', 'https://lefebresubastas.com',
 'Casa de subastas que combina tradición y vanguardia. Utiliza la plataforma Auction Mobility para pujas electrónicas.',
 '{
   "strategy": "pdf_selenium", 
   "frequency": "weekly",
   "urls": {
     "current": "https://lefebresubastas.com/subasta-en-curso/",
     "past": "https://lefebresubastas.com/subastas-anteriores/"
   },
   "requires_js": true
 }'::jsonb),

-- Spanish Houses  
('Durán Arte y Subastas', 'España', 'https://www.duran-subastas.com',
 'Casa de subastas líder y más antigua de España, fundada en 1969. Especializada en arqueología, pintura antigua y contemporánea.',
 '{
   "strategy": "html_static",
   "frequency": "daily", 
   "urls": {
     "upcoming": "https://www.duran-subastas.com/subasta-647-julio-2025",
     "historical": "https://www.duran-subastas.com/historico-de-subastas"
   }
 }'::jsonb),

('Setdart', 'España', 'https://www.setdart.com',
 'Primera subasta de arte online en España. Cuenta con más de 60.000 usuarios y combina el alcance global digital con presencia física.',
 '{
   "strategy": "html_ajax",
   "frequency": "daily",
   "urls": {
     "calendar": "https://www.setdart.com/es/subastas/calendario"
   }
 }'::jsonb),

('Ansorena', 'España', 'https://www.ansorena.com',
 'Fundada en 1845, comenzó como taller de joyería. Ofrece amplia gama de objetos de arte y antigüedades.',
 '{
   "strategy": "html_pdf",
   "frequency": "weekly",
   "urls": {
     "upcoming": "https://www.ansorena.com/noticias/subasta-de-septiembre-2025",
     "historical": "https://www.ansorena.com/historico"
   }
 }'::jsonb),

-- International Major Houses
('Christies', 'Estados Unidos', 'https://www.christies.com',
 'Fundada en 1766, empresa líder mundial con presencia en 46 países. Reconocida por sus subastas presenciales y en línea.',
 '{
   "strategy": "html_json",
   "frequency": "daily",
   "urls": {
     "calendar": "https://www.christies.com/en/calendar"
   },
   "requires_auth": false
 }'::jsonb),

('Sothebys', 'Estados Unidos', 'https://www.sothebys.com', 
 'Fundada en 1744, casa de subastas más antigua del mundo. Red global de 80 oficinas con ventas anuales superiores a 7 mil millones.',
 '{
   "strategy": "html_json",
   "frequency": "daily",
   "urls": {
     "calendar": "https://www.sothebys.com/en/calendar"
   },
   "requires_auth": false
 }'::jsonb),

('Bonhams', 'Reino Unido', 'https://www.bonhams.com',
 'Casa de subastas internacional fundada en Londres en 1793. Una de las más antiguas y grandes de arte, antigüedades y objetos raros.',
 '{
   "strategy": "html_static",
   "frequency": "daily", 
   "urls": {
     "upcoming": "https://www.bonhams.com/auctions/upcoming/"
   }
 }'::jsonb),

-- Latin American Houses
('Morton Subastas', 'México', 'https://www.mortonsubastas.com',
 'Abrió en 1988 como galería de antigüedades. Maneja importantes colecciones que ahora están en museos de México y extranjero.',
 '{
   "strategy": "html_static",
   "frequency": "daily",
   "urls": {
     "calendar": "https://live.mortonsubastas.com/en/auctions",
     "past": "https://live.mortonsubastas.com/en/auctions/past"
   }
 }'::jsonb),

('Casa Saráchaga', 'Argentina', 'https://www.sarachaga.com.ar',
 'Una de las casas más antiguas de Argentina, fundada en 1938. Comenzó con remates judiciales y evolucionó hacia arte y objetos de lujo.',
 '{
   "strategy": "html_static", 
   "frequency": "weekly",
   "urls": {
     "catalog": "https://www.sarachaga.com.ar/",
     "history": "https://www.sarachaga.com.ar/history"
   }
 }'::jsonb);

-- Insert initial categories
INSERT INTO categories (name, parent_category_id, level) VALUES
('Pintura', NULL, 0),
('Escultura', NULL, 0),
('Grabado', NULL, 0),
('Fotografía', NULL, 0),
('Joyería', NULL, 0),
('Mobiliario', NULL, 0),
('Arte Decorativo', NULL, 0),
('Libros y Manuscritos', NULL, 0),
('Vinos', NULL, 0),
('Automóviles', NULL, 0);

-- Subcategorías de Pintura
INSERT INTO categories (name, parent_category_id, level) VALUES
('Óleo sobre lienzo', 1, 1),
('Acuarela', 1, 1),
('Arte Moderno', 1, 1),
('Arte Contemporáneo', 1, 1),
('Arte Latinoamericano', 1, 1),
('Pintura Antigua', 1, 1);

-- Subcategorías de Escultura  
INSERT INTO categories (name, parent_category_id, level) VALUES
('Bronce', 2, 1),
('Mármol', 2, 1),
('Escultura Contemporánea', 2, 1);

-- Sample artists for testing
INSERT INTO artists (name, birth_year, death_year, nationality, movement, verified) VALUES
('Diego Rivera', 1886, 1957, 'Mexicana', 'Muralismo', true),
('Frida Kahlo', 1907, 1954, 'Mexicana', 'Surrealismo', true),
('Fernando Botero', 1932, 2023, 'Colombiana', 'Figurativismo', true),
('Salvador Dalí', 1904, 1989, 'Española', 'Surrealismo', true),
('Pablo Picasso', 1881, 1973, 'Española', 'Cubismo', true),
('Andy Warhol', 1928, 1987, 'Estadounidense', 'Pop Art', true),
('Emilio Pettoruti', 1892, 1971, 'Argentina', 'Cubismo', true),
('Julio Le Parc', 1928, NULL, 'Argentina', 'Arte Cinético', true);