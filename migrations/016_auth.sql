-- Login (S06): la contraseña temporal obliga a cambiarla en el primer acceso.
ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0;
