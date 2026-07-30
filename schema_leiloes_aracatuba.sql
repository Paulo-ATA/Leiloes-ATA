-- ==============================================================================
-- SCRIPT DE BANCO DE DADOS POSTGRESQL - LEILÕES DE IMÓVEIS (TRT-15 / ARAÇATUBA)
-- ==============================================================================

-- Habilita extensões para UUID e busca textual refinada
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ------------------------------------------------------------------------------
-- 1. TABELA: LEILOEIROS
-- Cadastra as casas de leilão oficial credenciadas pelo TRT-15
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leiloeiros (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome_leiloeiro VARCHAR(150) NOT NULL,
    site_url VARCHAR(255) NOT NULL UNIQUE,
    cnpj VARCHAR(18),
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 2. TABELA: IMOVEIS
-- Dados físicos e jurídicos da propriedade objeto da hasta
-- ------------------------------------------------------------------------------
CREATE TYPE tipo_imovel_enum AS ENUM (
    'CASA', 'APARTAMENTO', 'TERRENO', 'GALPAO', 'COMERCIAL', 'RURAL', 'OUTRO'
);

CREATE TYPE status_ocupacao_enum AS ENUM (
    'DESOCUPADO', 'OCUPADO', 'DESCONHECIDO'
);

CREATE TABLE IF NOT EXISTS imoveis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    titulo VARCHAR(255) NOT NULL,
    tipo_imovel tipo_imovel_enum DEFAULT 'OUTRO',
    endereco VARCHAR(255),
    bairro VARCHAR(100),
    cidade VARCHAR(100) NOT NULL DEFAULT 'Araçatuba',
    uf VARCHAR(2) NOT NULL DEFAULT 'SP',
    cep VARCHAR(9),
    area_total_m2 NUMERIC(10,2),
    area_privativa_m2 NUMERIC(10,2),
    matricula VARCHAR(50),
    cartorio VARCHAR(100),
    status_ocupacao status_ocupacao_enum DEFAULT 'DESCONHECIDO',
    percentual_propriedade NUMERIC(5,2) DEFAULT 100.00, -- Ex: 100.00% ou 50.00% (cota-parte)
    descricao_completa TEXT,
    observacoes_edital TEXT,
    coordenadas_gps POINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 3. TABELA: LEILOES
-- Dados do processo judicial na Justiça do Trabalho
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leiloes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    leiloeiro_id UUID REFERENCES leiloeiros(id) ON DELETE SET NULL,
    imovel_id UUID NOT NULL REFERENCES imoveis(id) ON DELETE CASCADE,
    numero_processo VARCHAR(50) NOT NULL, -- Ex: 0010123-45.2023.5.15.0011
    vara_origem VARCHAR(100) DEFAULT 'Divisão de Execução de Araçatuba',
    tribunal VARCHAR(20) DEFAULT 'TRT-15',
    link_lote_leiloeiro VARCHAR(500) NOT NULL UNIQUE,
    link_edital VARCHAR(500),
    link_laudo_avaliacao VARCHAR(500),
    link_matricula VARCHAR(500),
    aceita_parcelamento BOOLEAN DEFAULT FALSE,
    condicoes_parcelamento TEXT,
    debitos_iptu_subrogados BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 4. TABELA: HASTAS (PRAÇAS)
-- Mapeamento específico da 1ª e 2ª Hasta
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hastas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    leilao_id UUID NOT NULL REFERENCES leiloes(id) ON DELETE CASCADE,
    numero_hasta INT NOT NULL CHECK (numero_hasta IN (1, 2)),
    data_inicio TIMESTAMP WITH TIME ZONE NOT NULL,
    data_fim TIMESTAMP WITH TIME ZONE NOT NULL,
    valor_avaliacao NUMERIC(14,2) NOT NULL,
    valor_lance_minimo NUMERIC(14,2) NOT NULL,
    percentual_desagio NUMERIC(5,2) GENERATED ALWAYS AS (
        ROUND(((valor_avaliacao - valor_lance_minimo) / NULLIF(valor_avaliacao, 0)) * 100, 2)
    ) STORED,
    encerrado BOOLEAN DEFAULT FALSE,
    arrematado BOOLEAN DEFAULT FALSE,
    valor_arrematacao NUMERIC(14,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 5. TABELA: FILTROS_ALERTA
-- Configuração de preferências dos investidores/usuários
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS filtros_alerta (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome_usuario VARCHAR(100) NOT NULL,
    telegram_chat_id VARCHAR(50),
    email VARCHAR(150),
    valor_max_lance NUMERIC(14,2),
    desagio_minimo_pct NUMERIC(5,2) DEFAULT 40.00,
    apenas_desocupado BOOLEAN DEFAULT FALSE,
    apenas_segunda_hasta BOOLEAN DEFAULT TRUE,
    tipos_imovel tipo_imovel_enum[],
    bairros_interesse TEXT[], -- Ex: ARRAY['Ipanema', 'Centro', 'Bonsucesso']
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------------------
-- 6. INDEXAÇÃO PARA ALTÍSSIMA PERFORMANCE DE FILTRAGEM
-- ------------------------------------------------------------------------------
CREATE INDEX idx_imoveis_cidade ON imoveis(cidade);
CREATE INDEX idx_imoveis_bairro ON imoveis(bairro);
CREATE INDEX idx_imoveis_tipo ON imoveis(tipo_imovel);
CREATE INDEX idx_imoveis_ocupacao ON imoveis(status_ocupacao);

CREATE INDEX idx_hastas_data_fim ON hastas(data_fim);
CREATE INDEX idx_hastas_lance_minimo ON hastas(valor_lance_minimo);
CREATE INDEX idx_hastas_desagio ON hastas(percentual_desagio);
CREATE INDEX idx_hastas_numero ON hastas(numero_hasta);

CREATE INDEX idx_leiloes_processo ON leiloes(numero_processo);

-- Indexação Full Text Search na descrição do imóvel
CREATE INDEX idx_imoveis_busca_texto ON imoveis USING gin(to_tsvector('portuguese', titulo || ' ' || descricao_completa));

-- ------------------------------------------------------------------------------
-- 7. VIEW: PAINEL DE OPORTUNIDADES EM TEMPO REAL (ARAÇATUBA)
-- Query pronta para alimentar a API/Front-end
-- ------------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_oportunidades_aracatuba AS
SELECT 
    i.id AS imovel_id,
    i.titulo,
    i.tipo_imovel,
    i.bairro,
    i.cidade,
    i.status_ocupacao,
    i.percentual_propriedade,
    l.numero_processo,
    l.vara_origem,
    l.aceita_parcelamento,
    l.link_lote_leiloeiro,
    l.link_edital,
    l.link_laudo_avaliacao,
    h.id AS hasta_id,
    h.numero_hasta,
    h.data_inicio,
    h.data_fim,
    h.valor_avaliacao,
    h.valor_lance_minimo,
    h.percentual_desagio,
    lei.nome_leiloeiro
FROM imoveis i
JOIN leiloes l ON l.imovel_id = i.id
JOIN hastas h ON h.leilao_id = l.id
LEFT JOIN leiloeiros lei ON lei.id = l.leiloeiro_id
WHERE i.cidade ILIKE 'Araçatuba%'
  AND h.encerrado = FALSE
  AND h.data_fim >= CURRENT_TIMESTAMP
ORDER BY h.data_fim ASC, h.percentual_desagio DESC;
