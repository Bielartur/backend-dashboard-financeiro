# Alembic Migrations - Guia de Uso

## ✅ Configuração Completa

O Alembic está configurado e pronto para uso! Todas as mudanças no schema do banco de dados agora podem ser gerenciadas com migrações.

## Comandos Principais

### 1. Criar uma nova migração (após alterar os models)

```bash
uv run alembic revision --autogenerate -m "Descrição da mudança"
```

**Exemplo:**
```bash
uv run alembic revision --autogenerate -m "Add color column to categories"
```

Isso vai:
- Detectar automaticamente as mudanças nos models
- Criar um arquivo de migração em `alembic/versions/`

### 2. Aplicar migrações pendentes no banco

```bash
uv run alembic upgrade head
```

Isso aplica todas as migrações que ainda não foram executadas.

### 3. Reverter a última migração

```bash
uv run alembic downgrade -1
```

### 4. Ver histórico de migrações

```bash
uv run alembic history
```

### 5. Ver status atual do banco

```bash
uv run alembic current
```

## Workflow Típico

1. **Modificar um model** (ex: adicionar coluna em `Category`)
2. **Gerar migração**: `uv run alembic revision --autogenerate -m "Add icon to Category"`
3. **Revisar o arquivo** gerado em `alembic/versions/` (opcional mas recomendado)
4. **Aplicar no banco**: `uv run alembic upgrade head`

## Comparação com Django

| Django | Alembic |
|--------|---------|
| `python manage.py makemigrations` | `uv run alembic revision --autogenerate -m "message"` |
| `python manage.py migrate` | `uv run alembic upgrade head` |
| `python manage.py showmigrations` | `uv run alembic history` |

## Configuração Atual

- ✅ Todos os models importados (`User`, `Payment`, `Category`, `Bank`, `Alias`)
- ✅ DATABASE_URL lido automaticamente do `.env`
- ✅ Migração inicial criada

## Próximos Passos

Sempre que você modificar alguma entidade em `src/entities/`, basta rodar:

```bash
uv run alembic revision --autogenerate -m "Sua mensagem aqui"
uv run alembic upgrade head
```

E as mudanças serão aplicadas no banco automaticamente! 🎉
