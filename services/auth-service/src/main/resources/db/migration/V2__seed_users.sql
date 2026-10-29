-- Demo accounts, one per role (BCrypt cost 10). Passwords are listed in services/auth-service/README.md.
-- simulateur1 is the account the simulator uses to post transactions.
INSERT INTO users (id, username, password_hash, roles) VALUES
    (gen_random_uuid(), 'admin',       '$2a$10$JsRToKUPdxYsYziXz62AqObSwoeGbqZQAWdUbqhktCQqF1WvEaWmm', ARRAY['ADMIN']),
    (gen_random_uuid(), 'analyste1',   '$2a$10$1cngiIUWH5BJBz54.j7.l.kyppOP9QZQJfATUreJ73WZWINqTT93.', ARRAY['ANALYSTE']),
    (gen_random_uuid(), 'simulateur1', '$2a$10$LeDLgLUNtR5CtYSYBBXN3.gUazppzI74yw0t.QbST6hIrxLHfJr1u', ARRAY['SIMULATEUR']);
