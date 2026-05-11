from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np
import requests, json, os, io, time, random
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo

# ===========================
# CONFIGURAÇÕES BÁSICAS
# ===========================

meses = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

# TODOS OS ESTABELECIMENTOS
estabelecimentos = {
    '69355':  ['bLOw - ParkShopping Canoas',       'blowcanoas'],
    '42957':  ['bLOw - Moinhos de Ventos',         'blowmoinhos'],
    '81316':  ['bLOw - Menino Deus',               'blowmeninodeus'],
    '86857':  ['bLOw - Campo Grande',              'blowcampogrande'],
    '91228':  ['bLOw - Atlântida',                 'blowatlantida'],
    '91229':  ['bLOw - Balneário Camboriú',        'blowcamboriu'],
    '101605': ['bLOw - Zona Sul',                  'blowzonasul'],
    '101599': ['bLOw - Santa Maria',               'blowsantamaria'],
    '109731': ['bLOw - Cuiabá',                    'blowcuiaba'],
    '121476': ['bLOw - Novo Hamburgo',             'blownovohamburgo'],
    '121516': ['bLOw - Rio Branco',                'blowriobranco'],
    '121473': ['bLOw - Ribeirão Preto',            'blowribeiraopreto'],
    '123566': ['bLOw - Chapecó',                   'blowchapeco'],
    '133050': ['bLOw - Florianópolis',             'blowflorianopolis'],
    '136190': ['bLOw - São Leopoldo',              'blowsaoleopoldo'],

}

cadeiras = {
     'blowcanoas': 12,
    'blowmoinhos': 12,
    'blowmeninodeus': 8,
    'blowcampogrande': 8,
    'blowatlantida': 8,
    'blowcamboriu': 12,
    'blowzonasul': 9,
    'blowsantamaria': 12,
    'blowcuiaba': 12,
    'blownovohamburgo': 8,
    'blowriobranco': 15,
    'blowribeiraopreto': 12,
    'blowchapeco': 8,
    'blowflorianopolis': 12,
    'blowsaoleopoldo': 8,
}

# ===========================
# AUTENTICAÇÃO / SESSÃO
# ===========================

def doLogin():
    """
    Realiza login no Trinks e retorna uma requests.Session autenticada.
    """
    s = requests.Session()
    urlLogin = 'https://www.trinks.com/Login/AutenticarLogin'
    credentials = '{"email":"romulofigurelli@hotmail.com","senha":"05dezembro","returnUrl":""}'
    headers = {
        'Connection': 'keep-alive',
        'sec-ch-ua': '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
        'Accept': 'application/json, text/plain, */*',
        'DNT': '1',
        'Content-Type': 'application/json;charset=UTF-8',
        'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36',
        'sec-ch-ua-platform': '"Windows"',
        'Origin': 'https://www.trinks.com',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://www.trinks.com/Login',
        'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,es;q=0.6,la;q=0.5',
    }
    s.post(urlLogin, data=credentials, headers=headers)
    return s


def alteraEstabelecimento(s, idEstabelecimento: str):
    """
    Troca o estabelecimento autenticado na sessão.
    """
    urlLogin = 'https://www.trinks.com/Login/AlterarEstabelecimentoAutenticado'
    credentials = '{"idEstabelecimento":' + idEstabelecimento + '}'
    headers = {
        'Connection': 'keep-alive',
        'sec-ch-ua': '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
        'Accept': 'application/json, text/plain, */*',
        'DNT': '1',
        'Content-Type': 'application/json;charset=UTF-8',
        'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36',
        'sec-ch-ua-platform': '"Windows"',
        'Origin': 'https://www.trinks.com',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://www.trinks.com/Login',
        'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,es;q=0.6,la;q=0.5',
    }
    s.post(urlLogin, data=credentials, headers=headers)
    return s


def _request_with_retries(session, method, url, max_tries=6, base_sleep=1.5, relogin_fn=None, **kwargs):
    """
    Faz request com timeout padrão, retry exponencial + jitter.
    Se detectar HTML (login/erro) quando esperava JSON, tenta relogar 1x (se relogin_fn for passado).
    Retorna o response ou None.
    """
    if "timeout" not in kwargs:
        kwargs["timeout"] = (10, 90)  # (conexão, leitura)

    relogged = False
    for attempt in range(1, max_tries + 1):
        try:
            resp = session.request(method, url, **kwargs)

            # HTTPs típicos pra retry
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.6)
                print(f"⚠️ HTTP {resp.status_code} em {url} (tentativa {attempt}/{max_tries}). Retry em {wait:.1f}s…")
                time.sleep(wait)
                continue

            # Conteúdo HTML quando esperávamos JSON → sessão expirada ou bloqueio
            ct = resp.headers.get("Content-Type", "")
            if "text/html" in ct and relogin_fn and not relogged:
                print("⚠️ Recebi HTML (provável sessão expirada). Tentando relogar…")
                try:
                    new_s = relogin_fn()
                    if new_s is not None:
                        session = new_s
                        relogged = True
                except Exception as e:
                    print(f"Falha ao relogar: {e}")
                wait = base_sleep + random.uniform(0, 0.6)
                time.sleep(wait)
                continue

            return resp
        except requests.RequestException as e:
            wait = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.6)
            print(f"⚠️ Erro de rede {e.__class__.__name__} (tentativa {attempt}/{max_tries}). Retry em {wait:.1f}s…")
            time.sleep(wait)

    print(f"❌ Falha após {max_tries} tentativas: {url}")
    return None


# ===========================
# TRATAMENTO DE CSV (FINANCEIRO)
# ===========================

def _strip_financeiro_footer(csv_bytes: bytes, header_line_1idx: int) -> bytes:
    """
    Remove blocos extras do CSV de FINANCEIRO:
    - Linha 'Total (R$): ...'
    - Segunda tabela 'Resumo de Movimentação de Entradas e Saídas'
    Mantém apenas linhas com a mesma quantidade de colunas do cabeçalho principal.
    """
    txt = csv_bytes.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
    lines = txt.split("\n")
    if not lines:
        return csv_bytes

    # Descobre separador pelo header real
    hdr_idx0 = max(header_line_1idx - 1, 0)  # 0-index
    if hdr_idx0 >= len(lines):
        return csv_bytes
    sep = ";" if lines[hdr_idx0].count(";") >= lines[hdr_idx0].count(",") else ","

    header = lines[hdr_idx0]
    cols = header.count(sep)

    cleaned = [header]
    for l in lines[hdr_idx0 + 1:]:
        s = l.strip()
        if not s:
            continue
        # remove cabeçalho/linhas do segundo bloco
        if s.startswith("Total"):
            continue
        if s.startswith("Resumo de Movimentação"):
            continue
        if s.startswith("Data") and ("Abertura do Caixa" in s or "Abertura de Caixa" in s):
            continue
        # mantém somente linhas com mesma contagem de separadores do header principal
        if l.count(sep) != cols:
            continue
        cleaned.append(l)

    return ("\n".join(cleaned) + "\n").encode("utf-8")

def _write_csv_bytes_reencode(content: bytes, file: str, src_encoding_guess: str = "ISO-8859-1"):
    """
    Converte bytes vindos do Trinks (normalmente ISO-8859-1/Windows-1252)
    para UTF-8 com BOM, para ficar bonito no Excel/Power BI/VSCode.
    """
    os.makedirs(os.path.dirname(file), exist_ok=True)

    try:
        txt = content.decode(src_encoding_guess)
    except UnicodeDecodeError:
        # fallback: tenta decodificar como UTF-8, substituindo caracteres ruins
        txt = content.decode("utf-8", errors="replace")

    # grava sempre em UTF-8 com BOM
    with open(file, "w", encoding="utf-8-sig", newline="") as f:
        f.write(txt)



def _save_month_csv(content, ano, mes, tipo, slugEstabelecimento, overwrite=False):
    """
    tipo: 'faturamento' (header na linha 7) ou 'comissoes' (header na linha 8)
    Salva o CSV mensal, limpando rodapés/blocos extras quando necessário.

    🔹 Se o arquivo já existe:
        - Garante que o schema (colunas) continue igual ao do primeiro arquivo salvo.
        - Colunas extras vindas do Trinks são descartadas.
        - Colunas que faltam são criadas vazias.
    🔹 Nunca mais cria *_schema_diff_YYYYMM.csv.
    """
    import io
    import pandas as pd
    import os

    # — pastas / nomes —
    base_dir = f'{tipo}/batch/{ano}/{mes:02d}'
    os.makedirs(base_dir, exist_ok=True)
    file = f'{base_dir}/{slugEstabelecimento}.csv'

    # — mapeamento de linha de cabeçalho (1-indexed) —
    header_line_map = {
        "faturamento": 7,   # cabeçalho está na linha 7 (1-indexed)
        "comissoes": 8      # cabeçalho está na linha 8 (1-indexed)
    }
    header_line_1idx = header_line_map.get(tipo, 7)
    skip_before_header = max(header_line_1idx - 1, 0)

    # defaults
    skipfooter_rows = 1
    engine_to_use = "python"

    # normaliza quebras de linha
    try:
        content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    except Exception:
        pass

    if tipo == "faturamento":
        # Normaliza e limpa o rodapé/segunda tabela
        try:
            content = _strip_financeiro_footer(content, header_line_1idx)
            skip_before_header = 0
            skipfooter_rows = 0
            engine_to_use = "python"
        except Exception:
            skipfooter_rows = 0
            engine_to_use = "python"
    else:
        # comissões: mantém 1 linha de rodapé e engine python
        skipfooter_rows = 1
        engine_to_use = "python"

    # leitura robusta
    try:
        df = pd.read_csv(
            io.BytesIO(content),
            encoding="ISO-8859-1",
            sep=";",
            skiprows=skip_before_header,
            header=0,
            engine=engine_to_use,
            on_bad_lines="skip",
            skipfooter=skipfooter_rows
        )
    except Exception as e:
        print(f'Falha ao ler CSV (tipo={tipo}, {mes:02d}/{ano}): {e}')
        return

    # remove colunas totalmente vazias
    df = df.dropna(axis=1, how="all")

    # overwrite total?
    if overwrite and os.path.isfile(file):
        os.remove(file)
        print(f"Arquivo existente removido: {file}")

    # Se o arquivo já existe, alinhar o schema ao do arquivo existente
    if os.path.isfile(file):
        try:
            df_existing_head = pd.read_csv(file, sep=";", nrows=0, encoding="utf-8-sig")
            existing_cols = list(df_existing_head.columns)

            # adiciona colunas que existem no arquivo e não existem no df novo
            for col in existing_cols:
                if col not in df.columns:
                    df[col] = pd.NA

            # identifica colunas extras que vieram no df novo
            extra_cols = [c for c in df.columns if c not in existing_cols]
            if extra_cols:
                print(f"⚠️ Colunas extras descartadas em {slugEstabelecimento}: {extra_cols}")

            # mantém apenas as colunas do arquivo, na mesma ordem
            df = df[existing_cols]
        except Exception as e:
            print(f"⚠️ Não foi possível alinhar schema do existente: {e}")

    # grava (UTF-8 BOM p/ Excel)
    if not os.path.isfile(file):
        print(f'Escrevendo arquivo {file} pela primeira vez')
        df.to_csv(file, header=True, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    else:
        print(f'Inserindo dados novos no arquivo {file}')
        df.to_csv(file, mode="a", header=False, index=False, sep=";", decimal=",", encoding="utf-8-sig")

    print(f'Relatório CSV de {mes:02d}/{ano} salvo com sucesso em {file}')



# ===========================
# RELATÓRIO DE PROFISSIONAIS
# ===========================

def downloadRelatorioProfissionais(s, idEstabelecimento, slugEstabelecimento):
    """
    Baixa o CSV de profissionais (ativos+inativos) para um estabelecimento.

    Fluxos possíveis:
    1) Resposta JSON com "Dados" -> baixa CSV em DownloadCsvProfissionais (fluxo antigo).
    2) Resposta já em CSV (content-type texto/binário) -> salva direto.
    3) Resposta HTML / erro (403, etc.) -> loga e não derruba o script.

    Sempre regrava o arquivo final em UTF-8 com BOM.
    """
    url = 'https://www.trinks.com/BackOffice/Download/ExportarProfissionais'

    headers = {
        'Connection': 'keep-alive',
        'id-estabelecimento-autenticado': idEstabelecimento,
        'DNT': '1',
        'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/95.0.4638.69 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': '*/*',
        'X-Requested-With': 'XMLHttpRequest',
        'id-conta-logado': '278660',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua': '"Google Chrome";v="95", "Chromium";v="95", ";Not A Brand";v="99"',
        'Origin': 'https://www.trinks.com',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://www.trinks.com/BackOffice/ManterCadastro/Profissional',
        'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,es;q=0.6,la;q=0.5',
    }

    data = {
        'apenasAtivos': 'false'  # inclui profissionais inativos também
    }

    print(f'📥 Baixando profissionais de {slugEstabelecimento}...')

    # 1) POST principal com retry + relogin
    r = _request_with_retries(
        s,
        "POST",
        url,
        headers=headers,
        data=data,
        max_tries=6,
        base_sleep=1.5,
        relogin_fn=doLogin
    )

    if r is None:
        print(f"❌ Falha ao obter resposta de profissionais para {slugEstabelecimento}")
        return "Falha ao obter resposta de profissionais"

    ct = r.headers.get("Content-Type", "").lower()

    # 1.a) Se já veio CSV direto no POST
    if "text/csv" in ct or "application/octet-stream" in ct:
        file = f'profissionais/{slugEstabelecimento}.csv'
        try:
            _write_csv_bytes_reencode(r.content, file)
        except IOError:
            print("❌ Não foi possível escrever o arquivo de profissionais.")
            return 'Nao foi possivel escrever o arquivo de profissionais'
        else:
            print(f'✅ Relatório CSV de profissionais salvo com sucesso em {file}')
            return 'Relatorio CSV de profissionais salvo com sucesso (CSV direto)'

    # 1.b) Fluxo antigo: resposta em JSON com guid
    try:
        jsonResponse = json.loads(r.content)
    except json.JSONDecodeError:
        print(
            f"⚠️ Resposta não é JSON para profissionais de {slugEstabelecimento}. "
            f"Status {r.status_code}. Trecho: {r.text[:200]}"
        )
        return 'Resposta não JSON ao tentar exportar profissionais'

    if "Dados" not in jsonResponse or not jsonResponse["Dados"]:
        print(f"⚠️ Sem dados de profissionais para {slugEstabelecimento}")
        return 'Sem dados para retornar (profissionais)'

    dados = jsonResponse['Dados']
    urlDownload = (
        'https://www.trinks.com/BackOffice/Download/DownloadCsvProfissionais'
        f'?guidParaBuscarArquivoNaSessao={dados}'
    )

    # 2) GET do CSV com retry também
    downloadResponse = _request_with_retries(
        s,
        "GET",
        urlDownload,
        headers=headers,
        max_tries=6,
        base_sleep=1.5,
        relogin_fn=doLogin
    )

    if (downloadResponse is None
        or downloadResponse.status_code != 200
        or not downloadResponse.content):
        status = downloadResponse.status_code if downloadResponse is not None else "N/A"
        print(f"⚠️ Falha no download do CSV de profissionais ({slugEstabelecimento}). Status {status}")
        return 'Falha no download do CSV de profissionais'

    file = f'profissionais/{slugEstabelecimento}.csv'
    try:
        _write_csv_bytes_reencode(downloadResponse.content, file)
    except IOError:
        print("❌ Não foi possível escrever o arquivo de profissionais.")
        return 'Nao foi possivel escrever o arquivo de profissionais'
    else:
        print(f'✅ Relatório CSV de profissionais salvo com sucesso em {file}')
        return 'Relatorio CSV de profissionais salvo com sucesso'




# ===========================
# COMISSÕES - BATCH (POR MÊS)
# ===========================

def DownloadRelatorioComissoesBatch(s, idEstabelecimento, slugEstabelecimento, ano, mes=None, overwrite_all=False):
    """
    Se mes=None → roda todos os meses até o atual.
    Se mes=int → roda somente aquele mês.
    """
    TZ = ZoneInfo("America/Sao_Paulo")
    hoje = datetime.now(TZ).date()
    mesAtual = hoje.month
    anoAtual = hoje.year
    tipo = "comissoes"

    if ano < anoAtual:
        meses_para_processar = range(1, 13) if mes is None else [mes]
    else:
        meses_para_processar = range(1, mesAtual + 1) if mes is None else [mes]

    for m in meses_para_processar:
        primeiro_dia = date(ano, m, 1)
        ultimo_dia = (primeiro_dia + relativedelta(months=1)) - timedelta(days=1)

        if (ano == anoAtual and m == mesAtual):
            if hoje.day == 1:
                data_fim_date = primeiro_dia
            else:
                data_fim_date = min(hoje - timedelta(days=1), ultimo_dia)
        else:
            data_fim_date = ultimo_dia

        dataInicio = primeiro_dia.strftime("%d/%m/%Y")
        dataFim = data_fim_date.strftime("%d/%m/%Y")

        print('Periodo selecionado ', dataInicio, ' a ', dataFim)

        url = 'https://www.trinks.com/BackOffice/Download/ExportarComissoes'
        headers = {
            'id-estabelecimento-autenticado': idEstabelecimento,
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': '*/*',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.trinks.com/BackOffice/Relatorios/Comissoes'
        }

        data = {
            'TipoData': '1',
            'DataInicio': dataInicio,
            'DataFim': dataFim,
            'CodigoProfissional': '-1',
            'TipoItemPago': '0',
            'ExibirEstornos': 'false',
            'IdRelacaoProfissional': '0'
        }

        r = s.post(url, headers=headers, data=data)

        try:
            jsonResponse = json.loads(r.content)
        except json.JSONDecodeError:
            print(f'⚠️ Resposta não é JSON para {m:02d}/{ano}. Status {r.status_code}. Trecho: {r.text[:200]}')
            continue

        if "Dados" in jsonResponse and jsonResponse["Dados"]:
            dados = jsonResponse['Dados']
            urlDownload = f'https://www.trinks.com/BackOffice/Download/DownloadCsvRelatorios?guidParaBuscarArquivoNaSessao={dados}'
            downloadResponse = s.get(urlDownload, headers=headers)

            if downloadResponse.status_code != 200 or not downloadResponse.content:
                print(f'⚠️ Falha no download do CSV para {m:02d}/{ano}. Status {downloadResponse.status_code}')
                continue

            overwrite_this = overwrite_all or (ano == anoAtual and m == mesAtual)
            _save_month_csv(downloadResponse.content, ano, m, tipo, slugEstabelecimento, overwrite=overwrite_this)
        else:
            print(f"Sem dados para {m:02d}/{ano}")


# ===========================
# COMISSÕES - POR PERÍODO
# ===========================

def DownloadRelatorioComissoesPeriodo(s, idEstabelecimento, slugEstabelecimento, data_inicio: date, data_fim: date, write_mode="append"):
    """
    Baixa relatório de COMISSÕES para um período arbitrário [data_inicio, data_fim]
    e grava no arquivo mensal correspondente.

    write_mode: "overwrite" ou "append"
    """
    tipo = "comissoes"
    ano = data_inicio.year
    mes = data_inicio.month

    dataInicio = data_inicio.strftime("%d/%m/%Y")
    dataFim = data_fim.strftime("%d/%m/%Y")

    print(f"⬇️ Comissões {slugEstabelecimento}: {dataInicio} → {dataFim}")

    url = 'https://www.trinks.com/BackOffice/Download/ExportarComissoes'
    headers = {
        'id-estabelecimento-autenticado': idEstabelecimento,
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': '*/*',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://www.trinks.com/BackOffice/Relatorios/Comissoes'
    }

    data = {
        'TipoData': '1',
        'DataInicio': dataInicio,
        'DataFim': dataFim,
        'CodigoProfissional': '-1',
        'TipoItemPago': '0',
        'ExibirEstornos': 'false',
        'IdRelacaoProfissional': '0'
    }

    r = s.post(url, headers=headers, data=data)

    try:
        jsonResponse = json.loads(r.content)
    except json.JSONDecodeError:
        print(f'⚠️ Resposta não é JSON para {dataInicio}..{dataFim}. Status {r.status_code}. Trecho: {r.text[:200]}')
        return

    if "Dados" in jsonResponse and jsonResponse["Dados"]:
        dados = jsonResponse['Dados']
        urlDownload = f'https://www.trinks.com/BackOffice/Download/DownloadCsvRelatorios?guidParaBuscarArquivoNaSessao={dados}'
        downloadResponse = s.get(urlDownload, headers=headers)

        if downloadResponse.status_code != 200 or not downloadResponse.content:
            print(f'⚠️ Falha no download do CSV para {dataInicio}..{dataFim}. Status {downloadResponse.status_code}')
            return

        overwrite_flag = (write_mode == "overwrite")
        _save_month_csv(downloadResponse.content, ano, mes, tipo, slugEstabelecimento, overwrite=overwrite_flag)
    else:
        print(f"Sem dados para {dataInicio}..{dataFim}")


# ===========================
# FATURAMENTO (FINANCEIRO) - BATCH POR MÊS
# ===========================

def DownloadRelatorioFaturamentoBatch(s, idEstabelecimento, slugEstabelecimento, ano, mes=None, overwrite_all=False):
    """
    Se mes=None → roda todos os meses até o atual.
    Se mes=int → roda somente aquele mês.
    """
    TZ = ZoneInfo("America/Sao_Paulo")
    hoje = datetime.now(TZ).date()
    mesAtual = hoje.month
    anoAtual = hoje.year
    tipo = 'faturamento'

    if ano < anoAtual:
        meses_para_processar = range(1, 13) if mes is None else [mes]
    else:
        meses_para_processar = range(1, mesAtual + 1) if mes is None else [mes]

    for m in meses_para_processar:
        primeiro_dia = date(ano, m, 1)
        ultimo_dia = (primeiro_dia + relativedelta(months=1)) - timedelta(days=1)

        if (ano == anoAtual and m == mesAtual):
            if hoje.day == 1:
                data_fim_date = primeiro_dia
            else:
                data_fim_date = min(hoje - timedelta(days=1), ultimo_dia)
        else:
            data_fim_date = ultimo_dia

        dataInicio = primeiro_dia.strftime("%d/%m/%Y")
        dataFim = data_fim_date.strftime("%d/%m/%Y")

        print('Periodo selecionado ', dataInicio, ' a ', dataFim)

        url = 'https://www.trinks.com/BackOffice/Download/ExportarFinanceiro'
        headers = {
            'id-estabelecimento-autenticado': idEstabelecimento,
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': '*/*',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.trinks.com/BackOffice/Relatorios/Financeiro'
        }

        data = {
            'TipoData': '2',
            'DataInicio': dataInicio,
            'DataFim': dataFim,
            'TipoItemPago': '0',
            'TipoFiltroTransacaoProduto': '0',
            'IdFiltroPorDesconto': '0'
        }

        r = s.post(url, headers=headers, data=data)

        try:
            jsonResponse = json.loads(r.content)
        except json.JSONDecodeError:
            print(f'⚠️ Resposta não é JSON para {m:02d}/{ano}. Status {r.status_code}. Trecho: {r.text[:200]}')
            continue

        if "Dados" in jsonResponse and jsonResponse["Dados"]:
            dados = jsonResponse['Dados']
            urlDownload = f'https://www.trinks.com/BackOffice/Download/DownloadCsvRelatorios?guidParaBuscarArquivoNaSessao={dados}'
            downloadResponse = s.get(urlDownload, headers=headers)

            if downloadResponse.status_code != 200 or not downloadResponse.content:
                print(f'⚠️ Falha no download do CSV para {m:02d}/{ano}. Status {downloadResponse.status_code}')
                continue

            overwrite_this = overwrite_all or (ano == anoAtual and m == mesAtual)
            _save_month_csv(downloadResponse.content, ano, m, tipo, slugEstabelecimento, overwrite=overwrite_this)
        else:
            print(f"Sem dados para {m:02d}/{ano}")


# ===========================
# FATURAMENTO (FINANCEIRO) - POR PERÍODO
# ===========================

def DownloadRelatorioFaturamentoPeriodo(s, idEstabelecimento, slugEstabelecimento, data_inicio: date, data_fim: date, write_mode="append"):
    """
    Baixa relatório de FINANCEIRO (faturamento) para um período arbitrário [data_inicio, data_fim]
    e grava no arquivo mensal correspondente.

    write_mode: "overwrite" ou "append"
    """
    tipo = "faturamento"
    ano = data_inicio.year
    mes = data_inicio.month

    dataInicio = data_inicio.strftime("%d/%m/%Y")
    dataFim = data_fim.strftime("%d/%m/%Y")

    print(f"⬇️ Financeiro {slugEstabelecimento}: {dataInicio} → {dataFim}")

    url = 'https://www.trinks.com/BackOffice/Download/ExportarFinanceiro'
    headers = {
        'id-estabelecimento-autenticado': idEstabelecimento,
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': '*/*',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://www.trinks.com/BackOffice/Relatorios/Financeiro'
    }

    data = {
        'TipoData': '2',
        'DataInicio': dataInicio,
        'DataFim': dataFim,
        'TipoItemPago': '0',
        'TipoFiltroTransacaoProduto': '0',
        'IdFiltroPorDesconto': '0'
    }

    r = s.post(url, headers=headers, data=data)

    try:
        jsonResponse = json.loads(r.content)
    except json.JSONDecodeError:
        print(f'⚠️ Resposta não é JSON para {dataInicio}..{dataFim}. Status {r.status_code}. Trecho: {r.text[:200]}')
        return

    if "Dados" in jsonResponse and jsonResponse["Dados"]:
        dados = jsonResponse['Dados']
        urlDownload = f'https://www.trinks.com/BackOffice/Download/DownloadCsvRelatorios?guidParaBuscarArquivoNaSessao={dados}'
        downloadResponse = s.get(urlDownload, headers=headers)

        if downloadResponse.status_code != 200 or not downloadResponse.content:
            print(f'⚠️ Falha no download do CSV para {dataInicio}..{dataFim}. Status {downloadResponse.status_code}')
            return

        overwrite_flag = (write_mode == "overwrite")
        _save_month_csv(downloadResponse.content, ano, mes, tipo, slugEstabelecimento, overwrite=overwrite_flag)
    else:
        print(f"Sem dados para {dataInicio}..{dataFim}")


# ===========================
# PESQUISA DE SATISFAÇÃO (BATCH ANUAL)
# ===========================

def DownloadRelatorioPesquisaSatisfacaoBatch(s, idEstabelecimento, slugEstabelecimento, ano):
    hoje = date.today()
    mesAtual = int(hoje.strftime('%m'))
    anoAtual = int(hoje.strftime('%Y'))

    if ano < anoAtual:
        meses = 12
    else:
        meses = mesAtual

    for mes in range(1, meses + 1):
        if mes < 12:
            inicioAno = hoje.replace(day=1).replace(month=mes + 1).replace(year=ano)
            anoLoop = int(inicioAno.strftime('%Y'))
            dataFim = inicioAno.replace(day=1)
            dataFim = dataFim - timedelta(days=1)
            dataInicio = dataFim.replace(day=1)
            dataInicio = dataInicio.strftime("%d/%m/%Y")
            dataFim = dataFim.strftime("%d/%m/%Y")
            if mes == mesAtual and anoLoop == anoAtual:
                dataFim = hoje - timedelta(days=1)
                dataFim = dataFim.strftime("%d/%m/%Y")
        else:
            inicioAno = hoje.replace(day=1).replace(month=mes).replace(year=ano)
            anoLoop = int(inicioAno.strftime('%Y'))
            dataFim = inicioAno.replace(day=1)
            dataFim = dataFim - timedelta(days=1)
            dataFim = dataFim.replace(month=mes)
            dataFim = dataFim + timedelta(days=1)
            dataInicio = dataFim.replace(day=1).replace(month=mes)
            dataInicio = dataInicio.strftime("%d/%m/%Y")
            dataFim = dataFim.strftime("%d/%m/%Y")
            if mes == mesAtual and anoLoop == anoAtual:
                dataFim = hoje - timedelta(days=1)
                dataFim = hoje.strftime("%d/%m/%Y")

        print('Periodo selecionado ', dataInicio, ' a ', dataFim)
        url = 'https://www.trinks.com/Backoffice/Download/ExportarRelatorioDaPesquisaDeSatisfacao'
        headers = {
            'Connection': 'keep-alive',
            'id-estabelecimento-autenticado': idEstabelecimento,
            'DNT': '1',
            'sec-ch-ua-mobile': '?0',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36',
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'X-Requested-With': 'XMLHttpRequest',
            'id-conta-logado': '278660',
            'sec-ch-ua-platform': '"Windows"',
            'sec-ch-ua': '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
            'Origin': 'https://www.trinks.com',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': 'https://www.trinks.com/BackOffice/Avaliacoes/Relatorios',
            'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,es;q=0.6,la;q=0.5',
        }

        data = '{"NomeCliente":"","DataInicial":"'+dataInicio+'","DataFinal":"'+ dataFim +'","NomeServico":"","Notas":[1,2,3,4,5],"IncluirAvaliacoesNaoRespondidas":true,"Ordenacao":1}'
        r = s.post(url, headers=headers, data=data)
        jsonResponse = json.loads(r.content)
        if "Dados" in jsonResponse:
            dados = jsonResponse['Dados']
            urlDownload = f'https://www.trinks.com/BackOffice/Download/DownloadDeArquivo?guidParaBuscarArquivoNaSessao={dados}'
            downloadResponse = s.get(urlDownload, headers=headers)

            file = f'pesquisadesatisfacao/batch/{ano}/{slugEstabelecimento}.csv'
            staging = f'pesquisadesatisfacao/batch/{ano}/{slugEstabelecimento}_staging.csv'
            content = downloadResponse.content
            try:
                with open(staging, 'wb') as f:
                    f.write(content)
            except IOError:
                return 'Nao foi possivel escrever o arquivo'
            finally:
                df = pd.read_csv(staging, encoding="ISO-8859-1", sep=';')
                if not os.path.isfile(file):
                    print('Esrevendo arquivo ', file, ' pela primeira vez')
                    df.to_csv(file, header='column_names', index=False, sep=';', decimal=",", encoding="ISO-8859-1")
                else:
                    print('Inserindo dados novos no arquivo ', file)
                    df.to_csv(file, mode='a', header=False, index=False, sep=';', decimal=",", encoding="ISO-8859-1")
                os.remove(staging)
                print('Relatorio CSV de pesquisa de satisfação salvo com sucesso')


# ===========================
# CLIENTES
# ===========================

def DownloadRelatorioClientes(s, idEstabelecimento, slugEstabelecimento):
    """
    Baixa o CSV de clientes para um estabelecimento.

    Fluxos possíveis:
    1) Resposta JSON com "Dados" -> baixa CSV em DownloadCsvClientes (fluxo antigo).
    2) Resposta já em CSV (content-type texto/binário) -> salva direto.
    3) Resposta HTML / erro (403, etc.) -> loga e não derruba o script.
    Sempre regrava o arquivo final em UTF-8 com BOM.
    """
    hoje = date.today()
    dataFim = hoje - timedelta(days=1)
    dataInicio = hoje.replace(day=1).replace(month=1).replace(year=2019)
    dataInicio_str = dataInicio.strftime("%d/%m/%Y")
    dataFim_str = dataFim.strftime("%d/%m/%Y")

    url = "https://www.trinks.com/BackOffice/Download/ExportarClientes"

    headers = {
        "Connection": "keep-alive",
        "id-estabelecimento-autenticado": idEstabelecimento,
        "DNT": "1",
        "sec-ch-ua-mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/94.0.4606.81 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "id-conta-logado": "278660",
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua": '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
        "Origin": "https://www.trinks.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://www.trinks.com/BackOffice/Relatorios/Comissoes",
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,es;q=0.6,la;q=0.5",
    }

    data = [
        ("FiltroSelecionado", "0"),
        ("ConteudoFiltro", ""),
        ("Origem", "0"),
        ("ClientesPodemAgendarOnline", "0"),
        ("FiltroDataInicioCadastroCliente", dataInicio_str),
        ("FiltroDataFimCadastroCliente", dataFim_str),
        ("PeriodoAniversariante", ""),
        ("ClientesQueRecebemSMS", "0"),
        ("EnviarEmailAgendamentoCliente", "0"),
        ("ListaEtiquetaClienteEstabelecimento[0].IdEtiqueta", "8141"),
        ("ListaEtiquetaClienteEstabelecimento[0].Selecionado", "False"),
        ("ListaEtiquetaClienteEstabelecimento[1].IdEtiqueta", "17026"),
        ("ListaEtiquetaClienteEstabelecimento[1].Selecionado", "False"),
        ("ListaEtiquetaClienteEstabelecimento[2].IdEtiqueta", "7621"),
        ("ListaEtiquetaClienteEstabelecimento[2].Selecionado", "False"),
        ("ListaEtiquetaClienteEstabelecimento[3].IdEtiqueta", "7599"),
        ("ListaEtiquetaClienteEstabelecimento[3].Selecionado", "False"),
        ("ListaEtiquetaClienteEstabelecimento[4].IdEtiqueta", "7610"),
        ("ListaEtiquetaClienteEstabelecimento[4].Selecionado", "False"),
        ("ListaEtiquetaClienteEstabelecimento[5].IdEtiqueta", "11475"),
        ("ListaEtiquetaClienteEstabelecimento[5].Selecionado", "False"),
        ("ListaEtiquetaClienteEstabelecimento[6].IdEtiqueta", "9189"),
        ("ListaEtiquetaClienteEstabelecimento[6].Selecionado", "False"),
        ("FiltroPersonalizado.IdadeMinima", "0"),
        ("FiltroPersonalizado.IdadeMaxima", "0"),
        ("FiltroPersonalizado.Sexo", ""),
        ("FiltroPersonalizado.TipoPublicoAlvoServico", ""),
        ("FiltroPersonalizado.TipoDataServico", ""),
        ("FiltroPersonalizado.DataInicioServicoRealizado", ""),
        ("FiltroPersonalizado.DataFimServicoRealizado", ""),
        ("FiltroPersonalizado.DiasAntecedenciaServicoFeito", "0"),
        ("FiltroPersonalizado.PeriodoUltimaVisitaInicio", ""),
        ("FiltroPersonalizado.PeriodoUltimaVisitaFim", ""),
        ("FiltrarApenasAtivos", "true"),
        ("FiltrarApenasAtivos", "false"),
        ("FiltrarApenasAtivos", "true"),
        ("permiteAdicionarPontosAvulsos", "False"),
        ("ParametrosPaginacao.Pagina", "1"),
        ("ParametrosPaginacao.RegistrosPorPagina", "20"),
        ("ParametrosPaginacao.TotalItens", "20313"),
        ("MensagemRemocaoCliente", "O cliente selecionado será removido. Deseja continuar?"),
    ]

    print(f"📥 Baixando clientes de {slugEstabelecimento} ({dataInicio_str} a {dataFim_str})")

    # 1) POST principal
    r = _request_with_retries(
        s,
        "POST",
        url,
        headers=headers,
        data=data,
        max_tries=6,
        base_sleep=1.5,
        relogin_fn=doLogin,
    )

    if r is None:
        print(f"❌ Falha ao obter resposta de clientes para {slugEstabelecimento}")
        return "Falha ao obter resposta de clientes"

    ct = r.headers.get("Content-Type", "").lower()

    # 1.a) Se já veio CSV direto no POST
    if "text/csv" in ct or "application/octet-stream" in ct:
        file = f"clientes/{slugEstabelecimento}.csv"
        try:
            _write_csv_bytes_reencode(r.content, file)
        except IOError:
            print("❌ Não foi possível escrever o arquivo de clientes.")
            return "Nao foi possivel escrever o arquivo"
        else:
            print(f"✅ Relatório CSV de clientes salvo com sucesso em {file}")
            return "Relatorio CSV de clientes salvo com sucesso (CSV direto)"

    # 1.b) Fluxo antigo: resposta em JSON com guid
    try:
        jsonResponse = json.loads(r.content)
    except json.JSONDecodeError:
        print(
            f"⚠️ Resposta não é JSON para clientes de {slugEstabelecimento}. "
            f"Status {r.status_code}. Trecho: {r.text[:200]}"
        )
        return "Resposta não JSON ao tentar exportar clientes"

    if "Dados" not in jsonResponse or not jsonResponse["Dados"]:
        print(f"⚠️ Sem dados de clientes para {slugEstabelecimento}")
        return "Sem dados para retornar"

    dados = jsonResponse["Dados"]
    urlDownload = (
        "https://www.trinks.com/BackOffice/Download/DownloadCsvClientes"
        f"?guidParaBuscarArquivoNaSessao={dados}"
    )

    # 2) GET do CSV
    downloadResponse = _request_with_retries(
        s,
        "GET",
        urlDownload,
        headers=headers,
        max_tries=6,
        base_sleep=1.5,
        relogin_fn=doLogin,
    )

    if (
        downloadResponse is None
        or downloadResponse.status_code != 200
        or not downloadResponse.content
    ):
        status = downloadResponse.status_code if downloadResponse is not None else "N/A"
        print(f"⚠️ Falha no download do CSV de clientes ({slugEstabelecimento}). Status {status}")
        return "Falha no download do CSV de clientes"

    file = f"clientes/{slugEstabelecimento}.csv"
    try:
        _write_csv_bytes_reencode(downloadResponse.content, file)
    except IOError:
        print("❌ Não foi possível escrever o arquivo de clientes.")
        return "Nao foi possivel escrever o arquivo"
    else:
        print(f"✅ Relatório CSV de clientes salvo com sucesso em {file}")
        return "Relatorio CSV de clientes salvo com sucesso"





# ===========================
# DEMONSTRATIVO DE RESULTADO
# ===========================

def DownloadRelatorioDemonstrativoResultado(s, idEstabelecimento, slugEstabelecimento):
    hoje = date.today()
    dataInicioAno = date(2019, 1, 1)

    url = 'https://www.trinks.com/BackOffice/Download/ExportarDemonstrativoDeResultado'
    headers = {
        'Connection': 'keep-alive',
        'id-estabelecimento-autenticado': idEstabelecimento,
        'DNT': '1',
        'sec-ch-ua-mobile': '?0',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': '*/*',
        'X-Requested-With': 'XMLHttpRequest',
        'id-conta-logado': '278660',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua': '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
        'Origin': 'https://www.trinks.com',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://www.trinks.com/BackOffice/Relatorios/Comissoes',
        'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,es;q=0.6,la;q=0.5',
    }

    print(hoje)
    print(dataInicioAno)

    data = {
        'periodoInicial': str(dataInicioAno) + 'T00:00:00',
        'periodoFinal': str(hoje) + 'T00:00:00'
    }

    r = s.post(url, headers=headers, data=data)
    jsonResponse = json.loads(r.content)
    try:
        dados = jsonResponse['Dados']
    except KeyError:
        return 'Sem dados para retornar'

    urlDownload = f'https://www.trinks.com/BackOffice/Download/DownloadCsvRelatorios?guidParaBuscarArquivoNaSessao={dados}'
    downloadResponse = s.get(urlDownload, headers=headers)

    file = f'demonstrativoresultado/{slugEstabelecimento}.csv'
    content = downloadResponse.content
    try:
        with open(file, 'wb') as f:
            f.write(content)
    except IOError:
        return 'Nao foi possivel escrever o arquivo'
    finally:
        return 'Relatorio CSV de demonstrativo resultado salvo com sucesso'
