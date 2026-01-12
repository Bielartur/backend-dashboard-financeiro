# Dashboard Financeiro (Backend)

Este é o backend da aplicação de Dashboard Financeiro, desenvolvido em Python utilizando **FastAPI** para fornecer uma API RESTful de alta performance e fácil documentação.

## 🚀 Tecnologias Utilizadas

Este projeto foi construído com as seguintes tecnologias:

- **[Python](https://www.python.org/)** (v3.10+)
- **[FastAPI](https://fastapi.tiangolo.com/)**: Framework web moderno e rápido para construção de APIs.
- **[Pydantic](https://docs.pydantic.dev/)**: Validação de dados e gerenciamento de configurações.
- **[Uvicorn](https://www.uvicorn.org/)**: Servidor ASGI de alta performance.
- **[UV](https://github.com/astral-sh/uv)**: Gerenciador de projetos e pacotes Python incrivelmente rápido.
- **[SQLAlchemy](https://www.sqlalchemy.org/)**: Toolkit SQL e ORM (Object Relational Mapper).

## 📦 Pré-requisitos

Antes de começar, certifique-se de ter instalado em sua máquina:

- **[Python](https://www.python.org/downloads/)**
- **[UV](https://github.com/astral-sh/uv)** (Recomendado para gerenciamento de dependências e execução)

## 🛠️ Instalação

1. Clone o repositório:

```bash
git clone https://github.com/Bielartur/backend-dashboard-financeiro.git
cd backend-financas
```

2. Instale as dependências. Se estiver utilizando o **uv**:

```bash
uv sync
```

_Caso não utilize o uv, crie um ambiente virtual (`python -m venv .venv`) e instale via pip (`pip install -r requirements.txt`)._

## ▶️ Executando o Projeto

A maneira mais prática de rodar o servidor, se você estiver usando o `uv`, é:

```bash
uv run uvicorn main:app --reload
```

O servidor iniciará em `http://localhost:8000`.

## 📚 Documentação da API

O FastAPI fornece documentação interativa automática. Com o servidor rodando, acesse:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## 🔌 Frontend

Este backend serve dados para o frontend React. Certifique-se de que ambos estejam rodando para a aplicação funcionar completamente.

---

Desenvolvido com ❤️ para gestão financeira eficiente.
