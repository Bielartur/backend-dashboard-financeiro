# Testes Automatizados - Backend Finanças

Este diretório contém os testes automatizados da aplicação backend, desenvolvidos utilizando `pytest`.

## Arquitetura e Estrutura

A estrutura de testes espelha a estrutura do código fonte (`src`), facilitando a localização e manutenção dos testes.

```text
tests/
├── auth/           # Testes do módulo de autenticação
├── merchants/      # Testes do módulo de estabelecimentos
├── payments/       # Testes do módulo de pagamentos
└── conftest.py     # Configurações globais e Fixtures (Banco em memória, Client, Auth)
```

## Banco de Dados Isolado

Para garantir velocidade e segurança, não utilizamos o banco de dados de desenvolvimento local (PostgreSQL). Em vez disso, utilizamos um banco **SQLite em memória** (`sqlite:///:memory:`).

Isso significa que:

- Os dados criados nos testes não persistem.
- Não há risco de corromper seu banco de dados local.
- A execução é extremamente rápida.

## Como Executar os Testes

Certifique-se de ter as dependências instaladas (`pytest`, `httpx`, `pytest-asyncio`). Se estiver usando `uv`:

### Rodar todos os testes

```bash
uv run pytest
```

### Rodar testes de um módulo específico

```bash
uv run pytest tests/payments
```

### Rodar um arquivo específico

```bash
uv run pytest tests/payments/test_controller.py
```

### Ver output detalhado (Verbose)

```bash
uv run pytest -vv
```
