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

## Busca e relevância

A consulta ao Google Notícias e a nota que decide o e-mail não usam o nome e os termos do mesmo jeito.

**Busca.** Se "Termos de busca" estiver preenchido, o Google recebe só esse texto. O nome do assunto não entra na consulta. Se o campo estiver vazio, a busca usa o nome. Maiúsculas e minúsculas não mudam o resultado.

`OR` e `AND` são operadores do Google, não uma regra interna:

- `ChatGPT OR OpenAI` traz matéria com uma palavra ou com a outra.
- `ChatGPT AND OpenAI` pede as duas. O espaço entre palavras tem o mesmo efeito: `ChatGPT OpenAI`.

**Relevância.** A nota vai de 0 a 1 e usa as palavras do nome e dos termos juntos (3 letras ou mais; acentos são ignorados). Ela é calculada no título e no resumo do feed, antes de ler o texto da matéria. O resumo do Google quase sempre repete o título, então na prática a nota sai do título.

O ponto de partida é:

- **0,82** se a frase inteira do nome do assunto está no título.
- **0,62** se essa frase está só no resumo.
- **0,28** se a frase do nome não aparece.

Cada palavra encontrada soma um pedaço. No título, esse acréscimo vale no máximo 0,35, dividido pelo total de palavras. Uma palavra entre duas vale cerca de 0,18. Por isso um único termo de busca no título pode passar de 0,40 mesmo sem o nome do assunto na manchete.

**E-mail.** Entra no resumo a notícia com nota igual ou acima da relevância mínima (padrão 0,40), entre as mais altas do assunto, até o máximo configurado (padrão 5). Ela precisa ainda não ter sido enviada e ter sido coletada dentro da janela de horas (padrão 36). Abaixo do mínimo, a notícia continua na página **Notícias**.

A janela vira dias inteiros na consulta do Google (`when:2d` para 36 horas) e, em horas, corta o que é antigo demais. Notícia que já passou da janela permanece na página, mas não volta para o e-mail.

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
