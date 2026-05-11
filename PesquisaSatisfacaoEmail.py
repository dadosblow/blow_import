import os
import io
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import pandas as pd
import subprocess
from bs4 import BeautifulSoup


# =========================
# CONFIGURAÇÕES
# =========================
EMAIL_USER = os.getenv("EMAIL_USER", "BRUNO SPODE MACHADO")
EMAIL_PASS = os.getenv("EMAIL_PASS", "conner#01")
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")

# filtros
SENDER_FILTER = os.getenv("SENDER_FILTER", "automatico@trinks.com")
SUBJECT_FILTER = os.getenv(
    "SUBJECT_FILTER",
    "Relatorio pesquisa satisfacao diario - Email automatico"
)

# caminho local do repositório no GitHub Actions / ambiente local
REPO_PATH = os.getenv("REPO_PATH", os.getcwd())
DATA_PATH = os.path.join(REPO_PATH, "data")
CSV_CONSOLIDADO = os.path.join(DATA_PATH, "avaliacoes_consolidado.csv")
CSV_CONTROLE = os.path.join(DATA_PATH, "controle_processamento.csv")


# =========================
# FUNÇÕES AUXILIARES
# =========================
def decode_mime_words(value: str) -> str:
    if not value:
        return ""

    decoded_parts = decode_header(value)
    parts = []

    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            parts.append(part.decode(encoding or "utf-8", errors="ignore"))
        else:
            parts.append(part)

    return "".join(parts)


def ensure_files() -> None:
    os.makedirs(DATA_PATH, exist_ok=True)

    if not os.path.exists(CSV_CONSOLIDADO):
        pd.DataFrame(columns=[
            "Unidade",
            "Data do Atendimento",
            "Data da Avaliação",
            "Cliente",
            "Profissional",
            "Nota",
            "Comentário",
            "Valor",
            "Origem_Email",
            "Message_ID",
            "Data_Importacao"
        ]).to_csv(CSV_CONSOLIDADO, index=False, sep=";")

    if not os.path.exists(CSV_CONTROLE):
        pd.DataFrame(columns=[
            "Message_ID",
            "Data_Processamento",
            "Assunto",
            "Remetente",
            "Linhas_Importadas"
        ]).to_csv(CSV_CONTROLE, index=False, sep=";")


def load_processed_ids() -> set:
    if not os.path.exists(CSV_CONTROLE):
        return set()

    df = pd.read_csv(CSV_CONTROLE, sep=";")
    if "Message_ID" not in df.columns:
        return set()

    return set(df["Message_ID"].astype(str).dropna().tolist())


def save_control(message_id: str, subject: str, sender: str, rows: int) -> None:
    df = pd.read_csv(CSV_CONTROLE, sep=";")

    new_row = pd.DataFrame([{
        "Message_ID": message_id,
        "Data_Processamento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Assunto": subject,
        "Remetente": sender,
        "Linhas_Importadas": rows
    }])

    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CSV_CONTROLE, index=False, sep=";")


def parse_html_table(html_content: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table")

    if not tables:
        return None

    table_html = str(tables[0])

    try:
        dfs = pd.read_html(io.StringIO(table_html))
        return dfs[0] if dfs else None
    except ValueError:
        return None


def normalize_columns(df: pd.DataFrame, message_id: str) -> pd.DataFrame:
    rename_map = {
        "Unidade": "Unidade",
        "Data/Hora Atendimento": "Data do Atendimento",
        "Data/Hora Avaliação": "Data da Avaliação",
        "Nome do Cliente": "Cliente",
        "Nome Cliente": "Cliente",
        "Nome do Profissional": "Profissional",
        "Pesquisa de Satisfação": "Nota",
        "Observação do Cliente": "Comentário",
        "Valor gasto R$": "Valor"
    }

    df = df.rename(columns=rename_map)

    required = [
        "Unidade",
        "Data do Atendimento",
        "Data da Avaliação",
        "Cliente",
        "Profissional",
        "Nota",
        "Comentário",
        "Valor"
    ]

    for col in required:
        if col not in df.columns:
            df[col] = None

    df = df[required].copy()
    df["Origem_Email"] = "importacao_email_diaria"
    df["Message_ID"] = message_id
    df["Data_Importacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for col in ["Data do Atendimento", "Data da Avaliação"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    return df


def append_and_deduplicate(df_new: pd.DataFrame) -> None:
    if os.path.exists(CSV_CONSOLIDADO):
        df_old = pd.read_csv(CSV_CONSOLIDADO, sep=";")
    else:
        df_old = pd.DataFrame()

    for col in ["Data do Atendimento", "Data da Avaliação"]:
        if col in df_old.columns:
            df_old[col] = pd.to_datetime(df_old[col], errors="coerce")

    df = pd.concat([df_old, df_new], ignore_index=True)

    dedup_cols = [
        "Data do Atendimento",
        "Data da Avaliação",
        "Unidade",
        "Cliente",
        "Nota",
        "Profissional"
    ]
    dedup_cols = [c for c in dedup_cols if c in df.columns]

    df = df.drop_duplicates(subset=dedup_cols, keep="last")
    df = df.sort_values(
        by=["Data da Avaliação", "Unidade", "Cliente"],
        na_position="last"
    )

    df.to_csv(
        CSV_CONSOLIDADO,
        index=False,
        sep=";",
        date_format="%Y-%m-%d %H:%M:%S"
    )


def git_commit_and_push() -> None:
    subprocess.run(["git", "-C", REPO_PATH, "add", "."], check=True)

    status = subprocess.run(
        ["git", "-C", REPO_PATH, "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True
    )

    if not status.stdout.strip():
        print("Nenhuma alteração para commit.")
        return

    subprocess.run(
        [
            "git",
            "-C",
            REPO_PATH,
            "commit",
            "-m",
            f"Atualização automática avaliações {datetime.now():%Y-%m-%d %H:%M}"
        ],
        check=True
    )
    subprocess.run(["git", "-C", REPO_PATH, "push"], check=True)
    print("Push no GitHub realizado com sucesso.")


# =========================
# LEITURA DOS E-MAILS
# =========================
def fetch_emails() -> int:
    if not EMAIL_USER or not EMAIL_PASS:
        raise ValueError(
            "EMAIL_USER e EMAIL_PASS não foram definidos nas variáveis de ambiente."
        )

    ensure_files()
    processed_ids = load_processed_ids()

    mail = imaplib.IMAP4_SSL(IMAP_HOST)
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select(IMAP_FOLDER)

    since_date = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
    status, messages = mail.search(None, f'(SINCE "{since_date}")')

    if status != "OK":
        mail.logout()
        raise RuntimeError("Falha ao buscar e-mails na caixa.")

    email_ids = messages[0].split()
    imported_total = 0

    for email_id in reversed(email_ids):
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_mime_words(msg.get("Subject"))
        sender = msg.get("From", "")
        message_id = msg.get("Message-ID", "").strip()

        if not message_id or message_id in processed_ids:
            continue

        if SENDER_FILTER and SENDER_FILTER.lower() not in sender.lower():
            continue

        if SUBJECT_FILTER and SUBJECT_FILTER.lower() not in subject.lower():
            continue

        df_import = None

        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            filename = part.get_filename()
            content_type = part.get_content_type()

            if "attachment" in content_disposition.lower() and filename:
                filename = decode_mime_words(filename)
                payload = part.get_payload(decode=True)

                if filename.lower().endswith(".csv"):
                    df_import = pd.read_csv(io.BytesIO(payload), sep=None, engine="python")
                    break

                if filename.lower().endswith(".xlsx"):
                    df_import = pd.read_excel(io.BytesIO(payload))
                    break

            if content_type == "text/html" and df_import is None:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(errors="ignore")
                    df_import = parse_html_table(html)

        if df_import is None or df_import.empty:
            print(f"E-mail sem dados importáveis: {subject}")
            continue

        df_import = normalize_columns(df_import, message_id)

        ontem = (datetime.now() - timedelta(days=1)).date()
        if "Data da Avaliação" in df_import.columns:
            df_import = df_import[
                df_import["Data da Avaliação"].dt.date == ontem
            ]

        if df_import.empty:
            save_control(message_id, subject, sender, 0)
            continue

        append_and_deduplicate(df_import)
        save_control(message_id, subject, sender, len(df_import))
        imported_total += len(df_import)

        print(f"E-mail processado: {subject} | Linhas importadas: {len(df_import)}")

    mail.logout()
    return imported_total


if __name__ == "__main__":
    total = fetch_emails()
    print(f"Importação concluída. Linhas importadas: {total}")
    git_commit_and_push()
