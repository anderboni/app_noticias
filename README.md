# App Notícias

Sistema local em **Flask** que busca notícias sobre assuntos configurados, guarda o que encontrou e envia um resumo com links por e-mail nos horários escolhidos.

## O que o sistema faz

1. Na aba **Configurações**, o usuário cadastra um ou mais assuntos (incluir, editar, pausar ou excluir).
2. Define os horários do dia (Brasília) em que a coleta roda, e se isso vale só em dias úteis.
3. Informa os e-mails que recebem o resumo.
4. Em cada horário, o sistema consulta o Google Notícias, guarda as matérias e escolhe as mais relevantes.
5. O e-mail traz, por assunto, um resumo curto e o link de cada notícia.
6. A página **Notícias** lista tudo o que foi coletado, tenha ido ou não no e-mail.

O servidor SMTP continua no `.env`. Assuntos, horários e destinatários ficam no banco.

## Como rodar

```powershell
cd "c:\Users\ander\Documents\projetos\app_noticias"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
py run.py
```

Abra [http://127.0.0.1:5000](http://127.0.0.1:5000).

Na primeira subida há um horário às 08:00. Cadastre ao menos um assunto antes da coleta. O botão **Coletar e enviar resumo agora** dispara o mesmo fluxo do agendamento.

## Banco

SQLite em `noticias.db`. O arquivo antigo `financeiro.db` não é mais usado.

## API local

- `GET /api/health`
- `GET /api/topics`
- `GET /api/news`
- `GET /api/digests`
- `POST /api/collect`
