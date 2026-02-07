-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Research Papers table
CREATE TABLE IF NOT EXISTS research_papers (
    id SERIAL PRIMARY KEY,
    paper_id VARCHAR(100) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT[],
    source VARCHAR(50) NOT NULL,  -- pubmed, arxiv, core, europmc
    specialty VARCHAR(100),
    publication_date DATE,
    source_url TEXT,
    full_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Paper chunks for RAG
CREATE TABLE IF NOT EXISTS paper_chunks (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER REFERENCES research_papers(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),  -- all-MiniLM-L6-v2 dimension
    chunk_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create HNSW index for vector similarity search (works for any dataset size)
CREATE INDEX IF NOT EXISTS paper_chunks_embedding_idx 
ON paper_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Specialty index for filtering
CREATE INDEX IF NOT EXISTS paper_chunks_specialty_idx
ON paper_chunks USING btree ((chunk_metadata->>'specialty'));

-- HIPAA Audit Log table (tamper-proof design)
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    event_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    user_id VARCHAR(100),
    user_role VARCHAR(50),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    request_details JSONB,
    response_status INTEGER,
    phi_accessed BOOLEAN DEFAULT FALSE,
    previous_hash VARCHAR(64),
    current_hash VARCHAR(64) NOT NULL
);

-- Index for audit log queries
CREATE INDEX IF NOT EXISTS audit_logs_timestamp_idx ON audit_logs(event_timestamp);
CREATE INDEX IF NOT EXISTS audit_logs_user_idx ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS audit_logs_phi_idx ON audit_logs(phi_accessed) WHERE phi_accessed = TRUE;

-- Users table for RBAC
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'doctor', 'nurse', 'researcher')),
    specialty VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    mfa_enabled BOOLEAN DEFAULT FALSE,
    mfa_secret_encrypted BYTEA,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Doctor specialties lookup
CREATE TABLE IF NOT EXISTS specialties (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    pubmed_mesh_terms TEXT[],
    arxiv_categories TEXT[],
    description TEXT
);

-- Insert common medical specialties with search terms
INSERT INTO specialties (name, pubmed_mesh_terms, arxiv_categories) VALUES
    ('cardiology', ARRAY['Cardiology', 'Heart Diseases', 'Cardiovascular System'], ARRAY['q-bio.TO', 'q-bio.QM']),
    ('oncology', ARRAY['Oncology', 'Neoplasms', 'Cancer'], ARRAY['q-bio.CB', 'q-bio.TO']),
    ('neurology', ARRAY['Neurology', 'Nervous System Diseases', 'Brain Diseases'], ARRAY['q-bio.NC', 'q-bio.QM']),
    ('pulmonology', ARRAY['Pulmonary Medicine', 'Lung Diseases', 'Respiratory Tract Diseases'], ARRAY['q-bio.TO']),
    ('endocrinology', ARRAY['Endocrinology', 'Endocrine System Diseases', 'Diabetes Mellitus'], ARRAY['q-bio.MN']),
    ('gastroenterology', ARRAY['Gastroenterology', 'Digestive System Diseases', 'Gastrointestinal Diseases'], ARRAY['q-bio.TO']),
    ('nephrology', ARRAY['Nephrology', 'Kidney Diseases', 'Renal Insufficiency'], ARRAY['q-bio.TO']),
    ('rheumatology', ARRAY['Rheumatology', 'Rheumatic Diseases', 'Autoimmune Diseases'], ARRAY['q-bio.TO']),
    ('infectious_disease', ARRAY['Infectious Diseases', 'Communicable Diseases', 'Infection'], ARRAY['q-bio.PE', 'q-bio.MN']),
    ('pediatrics', ARRAY['Pediatrics', 'Child Health', 'Infant Health'], ARRAY['q-bio.TO'])
ON CONFLICT (name) DO NOTHING;

-- Patient context cache (encrypted at application layer)
CREATE TABLE IF NOT EXISTS patient_context (
    id SERIAL PRIMARY KEY,
    external_patient_id VARCHAR(255) NOT NULL,
    source_system VARCHAR(100) NOT NULL,  -- epic, cerner, mirth
    encrypted_data BYTEA NOT NULL,
    data_hash VARCHAR(64) NOT NULL,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE(external_patient_id, source_system)
);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables
CREATE TRIGGER update_research_papers_updated_at
    BEFORE UPDATE ON research_papers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
