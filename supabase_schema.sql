-- Supabase Database Schema Recreation Script
-- Generated from Django migrations in /Users/babawhizzo/Code/map_action_ml/Mapapi/Mapapi/migrations/
-- This script creates all tables and relationships to match the Django model state

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create custom types for ENUM fields
CREATE TYPE incident_status AS ENUM ('declared', 'resolved', 'in_progress', 'taken_into_account');
CREATE TYPE user_type AS ENUM ('admin', 'visitor', 'reporter', 'citizen', 'business', 'elu');
CREATE TYPE rapport_status AS ENUM ('new', 'in_progress', 'edit', 'canceled');
CREATE TYPE collaboration_status AS ENUM ('pending', 'approved', 'rejected');

-- Create tables in dependency order

-- 1. Category table
CREATE TABLE "Mapapi_category" (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(250) UNIQUE NOT NULL,
    photo VARCHAR(100),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Zone table
CREATE TABLE "Mapapi_zone" (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(250) UNIQUE NOT NULL,
    lattitude VARCHAR(250),
    longitude VARCHAR(250),
    photo VARCHAR(100),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Communaute table
CREATE TABLE "Mapapi_communaute" (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(250) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    zone_id BIGINT REFERENCES "Mapapi_zone"(id) ON DELETE CASCADE
);

-- 4. Indicateur table
CREATE TABLE "Mapapi_indicateur" (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(250) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. User table (custom auth)
CREATE TABLE "Mapapi_user" (
    id BIGSERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMPTZ,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    email VARCHAR(254) UNIQUE NOT NULL,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    date_joined TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    avatar VARCHAR(100) DEFAULT 'avatars/default.png',
    password_reset_count DECIMAL(10,0) DEFAULT 0,
    address VARCHAR(255),
    user_type user_type NOT NULL DEFAULT 'citizen',
    provider VARCHAR(255),
    organisation VARCHAR(255),
    points INTEGER DEFAULT 0,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    otp VARCHAR(6),
    otp_expiration TIMESTAMPTZ,
    verification_token UUID DEFAULT uuid_generate_v4(),
    community_id BIGINT REFERENCES "Mapapi_communaute"(id) ON DELETE CASCADE
);

-- 6. User zones many-to-many table
CREATE TABLE "Mapapi_user_zones" (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES "Mapapi_user"(id) ON DELETE CASCADE,
    zone_id BIGINT NOT NULL REFERENCES "Mapapi_zone"(id) ON DELETE CASCADE,
    UNIQUE(user_id, zone_id)
);

-- 7. User permissions many-to-many table (references Django auth)
CREATE TABLE "Mapapi_user_user_permissions" (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES "Mapapi_user"(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL,
    UNIQUE(user_id, permission_id)
);

-- 8. Incident table
CREATE TABLE "Mapapi_incident" (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(250),
    zone VARCHAR(250) NOT NULL,
    description TEXT,
    photo VARCHAR(100),
    video VARCHAR(100),
    audio VARCHAR(100),
    lattitude VARCHAR(250),
    longitude VARCHAR(250),
    etat incident_status NOT NULL DEFAULT 'declared',
    slug VARCHAR(250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    category_id BIGINT REFERENCES "Mapapi_category"(id) ON DELETE CASCADE,
    indicateur_id BIGINT REFERENCES "Mapapi_indicateur"(id) ON DELETE CASCADE,
    taken_by_id BIGINT REFERENCES "Mapapi_user"(id) ON DELETE SET NULL,
    user_id BIGINT REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 9. Incident categories many-to-many table
CREATE TABLE "Mapapi_incident_category_ids" (
    id BIGSERIAL PRIMARY KEY,
    incident_id BIGINT NOT NULL REFERENCES "Mapapi_incident"(id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL REFERENCES "Mapapi_category"(id) ON DELETE CASCADE,
    UNIQUE(incident_id, category_id)
);

-- 10. Evenement table
CREATE TABLE "Mapapi_evenement" (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255),
    zone VARCHAR(255) NOT NULL,
    description TEXT,
    photo VARCHAR(100),
    date TIMESTAMPTZ,
    lieu VARCHAR(250) NOT NULL,
    video VARCHAR(100),
    audio VARCHAR(100),
    latitude VARCHAR(1000),
    longitude VARCHAR(1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id BIGINT REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 11. Contact table
CREATE TABLE "Mapapi_contact" (
    id BIGSERIAL PRIMARY KEY,
    objet VARCHAR(250) NOT NULL,
    message TEXT,
    email VARCHAR(250),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 12. Message table
CREATE TABLE "Mapapi_message" (
    id BIGSERIAL PRIMARY KEY,
    objet VARCHAR(250) NOT NULL,
    message VARCHAR(250) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    communaute_id BIGINT REFERENCES "Mapapi_communaute"(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES "Mapapi_user"(id) ON DELETE CASCADE,
    zone_id BIGINT REFERENCES "Mapapi_zone"(id) ON DELETE CASCADE
);

-- 13. ResponseMessage table
CREATE TABLE "Mapapi_responsemessage" (
    id BIGSERIAL PRIMARY KEY,
    response VARCHAR(250) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    elu_id BIGINT REFERENCES "Mapapi_user"(id) ON DELETE CASCADE,
    message_id BIGINT REFERENCES "Mapapi_message"(id) ON DELETE CASCADE
);

-- 14. Rapport table
CREATE TABLE "Mapapi_rapport" (
    id BIGSERIAL PRIMARY KEY,
    details VARCHAR(500) NOT NULL,
    type VARCHAR(500),
    zone VARCHAR(250),
    date_livraison VARCHAR(100),
    statut rapport_status NOT NULL DEFAULT 'new',
    disponible BOOLEAN NOT NULL DEFAULT FALSE,
    file VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    incident_id BIGINT REFERENCES "Mapapi_incident"(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 15. Rapport incidents many-to-many table
CREATE TABLE "Mapapi_rapport_incidents" (
    id BIGSERIAL PRIMARY KEY,
    rapport_id BIGINT NOT NULL REFERENCES "Mapapi_rapport"(id) ON DELETE CASCADE,
    incident_id BIGINT NOT NULL REFERENCES "Mapapi_incident"(id) ON DELETE CASCADE,
    UNIQUE(rapport_id, incident_id)
);

-- 16. Participate table
CREATE TABLE "Mapapi_participate" (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evenement_id BIGINT REFERENCES "Mapapi_evenement"(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 17. Collaboration table
CREATE TABLE "Mapapi_collaboration" (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_date DATE,
    motivation TEXT,
    other_option VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    incident_id BIGINT NOT NULL REFERENCES "Mapapi_incident"(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 18. Colaboration table (appears to be duplicate/different spelling)
CREATE TABLE "Mapapi_colaboration" (
    id BIGSERIAL PRIMARY KEY,
    end_date DATE NOT NULL,
    motivation TEXT,
    other_option VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    incident_id BIGINT NOT NULL REFERENCES "Mapapi_incident"(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 19. Notification table
CREATE TABLE "Mapapi_notification" (
    id BIGSERIAL PRIMARY KEY,
    message VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read BOOLEAN NOT NULL DEFAULT FALSE,
    colaboration_id BIGINT NOT NULL REFERENCES "Mapapi_collaboration"(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 20. PasswordReset table
CREATE TABLE "Mapapi_passwordreset" (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(7) NOT NULL,
    date_created TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used BOOLEAN NOT NULL DEFAULT FALSE,
    date_used TIMESTAMPTZ,
    user_id BIGINT NOT NULL REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 21. UserAction table
CREATE TABLE "Mapapi_useraction" (
    id BIGSERIAL PRIMARY KEY,
    action VARCHAR(255) NOT NULL,
    "timeStamp" DATE NOT NULL DEFAULT CURRENT_DATE,
    user_id BIGINT NOT NULL REFERENCES "Mapapi_user"(id) ON DELETE CASCADE
);

-- 22. ImageBackground table
CREATE TABLE "Mapapi_imagebackground" (
    id BIGSERIAL PRIMARY KEY,
    photo VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 23. PhoneOTP table
CREATE TABLE "Mapapi_phoneotp" (
    id BIGSERIAL PRIMARY KEY,
    phone_number VARCHAR(15) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 24. ChatHistory table
CREATE TABLE "Mapapi_chathistory" (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL
);

-- 25. Prediction table (with final field modifications from migrations)
CREATE TABLE "Mapapi_prediction" (
    id BIGSERIAL PRIMARY KEY,
    prediction_id INTEGER UNIQUE,
    incident_id VARCHAR(255) NOT NULL,
    incident_type VARCHAR(255) NOT NULL,
    piste_solution TEXT NOT NULL,
    analysis TEXT NOT NULL,
    ndvi_heatmap TEXT,
    ndvi_ndwi_plot TEXT,
    landcover_plot TEXT
);

-- Create indexes for better performance
CREATE INDEX ON "Mapapi_user" (email);
CREATE INDEX ON "Mapapi_incident" (zone);
CREATE INDEX ON "Mapapi_incident" (etat);
CREATE INDEX ON "Mapapi_evenement" (zone);
CREATE INDEX ON "Mapapi_chathistory" (session_id);
CREATE INDEX ON "Mapapi_chathistory" (question);
CREATE INDEX ON "Mapapi_chathistory" (answer);
CREATE INDEX ON "Mapapi_passwordreset" (code);
CREATE INDEX ON "Mapapi_user" (is_verified);
CREATE INDEX ON "Mapapi_user" (user_type);

-- Add foreign key constraints that reference external Django tables (commented out for Supabase)
-- These would need to be handled separately if you're migrating from a full Django setup
-- ALTER TABLE "Mapapi_user_user_permissions" ADD CONSTRAINT fk_permission 
--     FOREIGN KEY (permission_id) REFERENCES auth_permission(id);

-- Create Row Level Security policies if needed (uncomment as required)
-- ALTER TABLE "Mapapi_user" ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE "Mapapi_incident" ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE "Mapapi_evenement" ENABLE ROW LEVEL SECURITY;

-- Grant permissions (adjust as needed for your Supabase setup)
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
-- GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Insert any initial data if needed
-- INSERT INTO "Mapapi_category" (name, description) VALUES 
--     ('Infrastructure', 'Infrastructure related incidents'),
--     ('Environment', 'Environmental issues'),
--     ('Security', 'Security related incidents');

COMMIT;
