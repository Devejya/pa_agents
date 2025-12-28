-- ============================================================================
-- User Relationship Graph Schema
-- PostgreSQL implementation with migration path to Neptune/Neo4j
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- Enums
-- ============================================================================

CREATE TYPE person_status AS ENUM ('active', 'deceased', 'blocked', 'archived');
CREATE TYPE relationship_category AS ENUM ('family', 'friends', 'work', 'acquaintance');
CREATE TYPE interest_type AS ENUM (
    'sport', 'videogame', 'arts', 'crafts', 'reading', 'writing', 
    'fiction', 'travel', 'food', 'tv', 'movies', 'music', 
    'outdoors', 'technology', 'other'
);

-- ============================================================================
-- Persons Table (Graph Nodes)
-- ============================================================================

CREATE TABLE persons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Core identity
    name VARCHAR(200) NOT NULL,
    aliases TEXT[] DEFAULT '{}',  -- Stored lowercase
    is_core_user BOOLEAN DEFAULT FALSE,
    status person_status DEFAULT 'active',
    
    -- Contact information
    work_email VARCHAR(254),
    personal_email VARCHAR(254),
    work_cell VARCHAR(20),      -- E.164 format: +15551234567
    personal_cell VARCHAR(20),
    secondary_cell VARCHAR(20),
    
    -- Professional info
    company VARCHAR(200),
    latest_title VARCHAR(200),
    expertise VARCHAR(500),
    
    -- Location
    address VARCHAR(500),
    country VARCHAR(100),  -- Made nullable for discovered contacts
    city VARCHAR(100),
    state VARCHAR(100),
    
    -- Social
    instagram_handle VARCHAR(100),
    
    -- Demographics
    religion VARCHAR(100),
    ethnicity VARCHAR(100),
    country_of_birth VARCHAR(100),
    city_of_birth VARCHAR(100),
    
    -- Interests (denormalized JSONB array)
    interests JSONB DEFAULT '[]',
    
    -- Full-text search vector (auto-updated via trigger)
    search_vector tsvector,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT contact_method_required CHECK (
        personal_cell IS NOT NULL OR 
        work_cell IS NOT NULL OR 
        work_email IS NOT NULL OR 
        personal_email IS NOT NULL
    ),
    CONSTRAINT title_requires_company CHECK (
        latest_title IS NULL OR company IS NOT NULL
    )
);

-- Indexes for persons
CREATE INDEX idx_persons_name ON persons (LOWER(name));
CREATE INDEX idx_persons_aliases ON persons USING GIN (aliases);
CREATE INDEX idx_persons_is_core_user ON persons (is_core_user) WHERE is_core_user = TRUE;
CREATE INDEX idx_persons_status ON persons (status);
CREATE INDEX idx_persons_work_email ON persons (LOWER(work_email)) WHERE work_email IS NOT NULL;
CREATE INDEX idx_persons_personal_email ON persons (LOWER(personal_email)) WHERE personal_email IS NOT NULL;
CREATE INDEX idx_persons_interests ON persons USING GIN (interests);
CREATE INDEX idx_persons_search_vector ON persons USING GIN (search_vector);

-- ============================================================================
-- Relationships Table (Graph Edges)
-- ============================================================================

CREATE TABLE relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Edge endpoints (single edge with role pair)
    from_person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    to_person_id UUID NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    
    -- Relationship type
    category relationship_category NOT NULL,
    from_role VARCHAR(100) NOT NULL,  -- What from_person is to to_person
    to_role VARCHAR(100) NOT NULL,    -- What to_person is to from_person
    
    -- Connection counts (embedded JSONB)
    connection_counts JSONB DEFAULT '{
        "call_count_past_year": 0,
        "call_count_past_six_months": 0,
        "call_count_past_three_months": 0,
        "call_count_past_one_month": 0,
        "call_count_past_one_week": 0,
        "call_count_past_one_day": 0,
        "meet_count_past_six_months": 0,
        "meet_count_past_three_months": 0,
        "meet_count_past_one_month": 0,
        "meet_count_past_one_week": 0,
        "meet_count_past_one_day": 0,
        "text_count_past_six_months": 0,
        "text_count_past_three_months": 0,
        "text_count_past_one_month": 0,
        "text_count_past_one_week": 0,
        "text_count_past_one_day": 0,
        "last_call_at": null,
        "last_text_at": null,
        "last_meet_at": null
    }',
    
    -- Shared interests (list of interest names)
    similar_interests TEXT[] DEFAULT '{}',
    
    -- Timeline
    first_meeting_date DATE,
    length_of_relationship_years INTEGER,
    length_of_relationship_days INTEGER,
    
    -- Status (for historical relationships)
    is_active BOOLEAN DEFAULT TRUE,
    ended_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT no_self_relationship CHECK (from_person_id != to_person_id)
);

-- Indexes for relationships
CREATE INDEX idx_relationships_from_person ON relationships (from_person_id);
CREATE INDEX idx_relationships_to_person ON relationships (to_person_id);
CREATE INDEX idx_relationships_category ON relationships (category);
CREATE INDEX idx_relationships_from_role ON relationships (LOWER(from_role));
CREATE INDEX idx_relationships_to_role ON relationships (LOWER(to_role));
CREATE INDEX idx_relationships_is_active ON relationships (is_active);

-- Composite index for bidirectional lookups
CREATE INDEX idx_relationships_persons ON relationships (from_person_id, to_person_id);

-- ============================================================================
-- Audit Log Table
-- ============================================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    actor_id VARCHAR(255) NOT NULL,  -- Who performed the action
    action VARCHAR(50) NOT NULL,     -- read, write, delete
    resource_type VARCHAR(50) NOT NULL,  -- person, relationship
    resource_id VARCHAR(255) NOT NULL,
    fields_accessed TEXT[] DEFAULT '{}',
    context JSONB
);

-- Index for querying audit logs
CREATE INDEX idx_audit_logs_timestamp ON audit_logs (timestamp DESC);
CREATE INDEX idx_audit_logs_actor ON audit_logs (actor_id);
CREATE INDEX idx_audit_logs_resource ON audit_logs (resource_type, resource_id);

-- ============================================================================
-- Functions and Triggers
-- ============================================================================

-- Function to update search vector for full-text search
CREATE OR REPLACE FUNCTION update_person_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(array_to_string(NEW.aliases, ' '), '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.expertise, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.company, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.latest_title, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(
            (SELECT string_agg(interest->>'name', ' ') FROM jsonb_array_elements(NEW.interests) AS interest),
            ''
        )), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update search vector
CREATE TRIGGER trigger_update_person_search_vector
    BEFORE INSERT OR UPDATE ON persons
    FOR EACH ROW
    EXECUTE FUNCTION update_person_search_vector();

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER trigger_persons_updated_at
    BEFORE UPDATE ON persons
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trigger_relationships_updated_at
    BEFORE UPDATE ON relationships
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: All relationships from core user's perspective
CREATE VIEW core_user_relationships AS
SELECT 
    p_core.id AS core_user_id,
    p_core.name AS core_user_name,
    r.category,
    r.from_role AS core_user_is,
    r.to_role AS contact_is,
    p_contact.id AS contact_id,
    p_contact.name AS contact_name,
    p_contact.aliases AS contact_aliases,
    p_contact.personal_cell AS contact_personal_cell,
    p_contact.work_cell AS contact_work_cell,
    p_contact.personal_email AS contact_personal_email,
    p_contact.work_email AS contact_work_email,
    p_contact.interests AS contact_interests,
    r.connection_counts,
    r.is_active
FROM persons p_core
JOIN relationships r ON p_core.id = r.from_person_id
JOIN persons p_contact ON r.to_person_id = p_contact.id
WHERE p_core.is_core_user = TRUE AND r.is_active = TRUE;

-- ============================================================================
-- Sample Data (for testing)
-- ============================================================================

-- Uncomment to insert sample data:
/*
-- Core user
INSERT INTO persons (name, aliases, is_core_user, personal_email, personal_cell, country)
VALUES ('John Doe', ARRAY['me', 'john'], TRUE, 'john@personal.com', '+15551234567', 'USA');

-- Sister
INSERT INTO persons (name, aliases, personal_email, personal_cell, country, interests)
VALUES (
    'Jane Doe', 
    ARRAY['jane', 'sis'], 
    'jane@personal.com', 
    '+15559876543', 
    'USA',
    '[{"id": "550e8400-e29b-41d4-a716-446655440000", "name": "skiing", "type": "sport", "level": 85}]'::jsonb
);

-- Create relationship
INSERT INTO relationships (from_person_id, to_person_id, category, from_role, to_role)
SELECT 
    (SELECT id FROM persons WHERE name = 'John Doe'),
    (SELECT id FROM persons WHERE name = 'Jane Doe'),
    'family',
    'brother',
    'sister';
*/

