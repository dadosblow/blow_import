from blow import (
    doLogin,
    alteraEstabelecimento,
    estabelecimentos,
    _save_month_csv,
)
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
import pandas as pd
import os
import json
import time
import requests  # 👈 novo: vamos usar diretamente
# import random  # não precisamos mais

# ========================
# CONFIGURAÇÕES
# ========================
USE_CURRENT_MONTH = True    # True = sempre mês corrente; False = usa ANO/MES fixos abaixo
ANO = 2025                  # usado se USE_CURRENT_MONTH = False
MES = 11                    # usado se USE_CURRENT_MONTH = False

DAYS_STEP = 5               # tamanho da janela em dias (5 em 5 dias)
BLOCO_TAMANHO = 8           # quantos estabelecimentos por bloco (pra evitar 403)
SLEEP_ENTRE_BLOCOS = 120    # segundos de pausa entre blocos
SLEEP_ENTRE_LOJAS = 1       # pausa pequena entre lojas

MAX_TENTATIVAS_FAIXA = 3    # quantas vezes tentar a MESMA faixa ao pegar erro/HTML
TEVE_403 = False            # flag global para avisar no final se teve 403


def get_last_loaded_date(tipo: str, ano: int, mes: int, slug: str) -> date | None:
    """
    Lê o CSV existente (tipo/batch/ano/mes/slug.csv) e retorna a última
    data carregada usando especificamente a coluna 'Data de Atendimento/Venda'.
    """

    path = f"{tipo}/batch/{ano}/{mes:02d}/{slug}.csv"
    if not os.path.isfile(path):
        return None

    try:
        df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    except Exception as e:
        print(f"⚠️ Não consegui ler {path} ({e}).")
        return None

    if "Data de Atendimento/Venda" not in df.columns:
        print(f"⚠️ CSV não contém a coluna 'Data de Atendimento/Venda'.")
        return None

    try:
        dt_series = pd.to_datetime(
            df["Data de Atendimento/Venda"],
            dayfirst=True,
            errors="coerce"
        ).dropna()
    except Exception as e:
        print(f"⚠️ Erro ao converter datas ({e}).")
        return None

    if dt_series.empty:
        return None

    return dt_series.max().date()


def baixar_financeiro_periodo(
    sessao,
    idEstabelecimento: str,
    slugEstabelecimento: str,
    data_inicio: date,
    data_fim: date,
):
    """
    Baixa o relatório de FINANCEIRO para o período [data_inicio, data_fim]
    e faz append no CSV daquele mês.

    👉 Se der 403/HTML, reloga e tenta novamente a MESMA faixa,
       até MAX_TENTATIVAS_FAIXA vezes.

    Retorna SEMPRE a sessão (que pode ter sido recriada).
    """
    global TEVE_403

    tipo = "faturamento"
    ano = data_inicio.year
    mes = data_inicio.month

    dataInicio_str = data_inicio.strftime("%d/%m/%Y")
    dataFim_str = data_fim.strftime("%d/%m/%Y")

    url = "https://www.trinks.com/BackOffice/Download/ExportarFinanceiro"

    for tentativa in range(1, MAX_TENTATIVAS_FAIXA + 1):
        print(
            f"⬇️ Financeiro {slugEstabelecimento}: "
            f"{dataInicio_str} → {dataFim_str} (tentativa {tentativa})"
        )

        headers = {
            "id-estabelecimento-autenticado": idEstabelecimento,
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.trinks.com/BackOffice/Relatorios/Financeiro",
        }

        data = {
            "TipoData": "2",  # ok para Financeiro
            "DataInicio": dataInicio_str,
            "DataFim": dataFim_str,
            "TipoItemPago": "0",
            "TipoFiltroTransacaoProduto": "0",
            "IdFiltroPorDesconto": "0",
        }

        # POST
        try:
            r = sessao.post(url, headers=headers, data=data, timeout=(10, 90))
        except requests.RequestException as e:
            print(f"⚠️ Erro de rede ao chamar ExportarFinanceiro: {e}")
            time.sleep(2)
            continue

        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct or r.status_code == 403:
            # sessão provavelmente bloqueada/expirada
            TEVE_403 = True
            print("⚠️ Recebi HTML (provável sessão expirada ou bloqueada). Tentando relogar…")

            try:
                sessao.close()
            except Exception:
                pass

            # novo login + troca de estabelecimento
            sessao = doLogin()
            alteraEstabelecimento(sessao, idEstabelecimento)
            time.sleep(2)
            # volta para o início do loop: tenta MESMA faixa de novo
            continue

        # tenta ler JSON
        try:
            jsonResponse = json.loads(r.content)
        except json.JSONDecodeError:
            print(
                f"⚠️ Resposta não é JSON para {dataInicio_str}..{dataFim_str}. "
                f"Status {r.status_code}. Trecho: {r.text[:200]}"
            )
            return sessao

        if "Dados" not in jsonResponse or not jsonResponse["Dados"]:
            print(f"Sem dados para {dataInicio_str}..{dataFim_str}")
            return sessao

        dados = jsonResponse["Dados"]
        urlDownload = (
            "https://www.trinks.com/BackOffice/Download/DownloadCsvRelatorios"
            f"?guidParaBuscarArquivoNaSessao={dados}"
        )

        # GET do CSV
        try:
            downloadResponse = sessao.get(urlDownload, headers=headers, timeout=(10, 90))
        except requests.RequestException as e:
            print(f"⚠️ Erro de rede ao baixar CSV: {e}")
            time.sleep(2)
            continue

        if downloadResponse.status_code != 200 or not downloadResponse.content:
            print(
                f"⚠️ Falha no download do CSV para {dataInicio_str}..{dataFim_str}. "
                f"Status {downloadResponse.status_code}"
            )
            time.sleep(2)
            continue

        # sucesso: salva e sai
        _save_month_csv(downloadResponse.content, ano, mes, tipo, slugEstabelecimento, overwrite=False)
        return sessao

    # Se chegou aqui, tentou MAX_TENTATIVAS_FAIXA vezes e não conseguiu
    print(f"❌ Desisti da faixa {dataInicio_str}..{dataFim_str} após {MAX_TENTATIVAS_FAIXA} tentativas.")
    return sessao


def gerar_periodos(data_inicio: date, data_fim: date, step_dias: int):
    """
    Gera pares (inicio, fim) de step_dias em step_dias até data_fim.
    """
    inicio = data_inicio
    while inicio <= data_fim:
        fim = min(inicio + timedelta(days=step_dias - 1), data_fim)
        yield inicio, fim
        inicio = fim + timedelta(days=1)


def processar_estabelecimento(
    idEstabelecimento: str,
    slugEstabelecimento: str,
    ano: int,
    mes: int,
):
    """
    Faz carga incremental de FINANCEIRO para 1 estabelecimento:
    - Lê última data no CSV (se existir)
    - Monta período alvo do mês (até ontem ou fim do mês)
    - Baixa apenas os dias faltantes em janelas de DAYS_STEP
    """
    TZ = ZoneInfo("America/Sao_Paulo")
    hoje_sp = datetime.now(TZ).date()

    primeiro_dia_mes = date(ano, mes, 1)
    ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)

    # define data final alvo do mês
    if ano == hoje_sp.year and mes == hoje_sp.month:
        if hoje_sp.day == 1:
            # dia 01 ainda não tem mês corrente "completo" → não faz nada
            print(f"📅 {slugEstabelecimento}: hoje é dia 01, nada para carregar ainda do mês {mes:02d}/{ano}.")
            return
        data_fim_alvo = min(hoje_sp - timedelta(days=1), ultimo_dia_mes)
    else:
        data_fim_alvo = ultimo_dia_mes

    # última data que já está no CSV
    ultima_data = get_last_loaded_date("faturamento", ano, mes, slugEstabelecimento)

    if ultima_data is None:
        data_inicio_nova = primeiro_dia_mes
        print(
            f"📂 {slugEstabelecimento}: arquivo ainda não existe ou sem data válida. "
            f"Vai carregar desde {data_inicio_nova.strftime('%d/%m/%Y')}."
        )
    else:
        data_inicio_nova = ultima_data + timedelta(days=1)
        print(
            f"📂 {slugEstabelecimento}: última data carregada = {ultima_data.strftime('%d/%m/%Y')}. "
            f"Vai carregar a partir de {data_inicio_nova.strftime('%d/%m/%Y')}."
        )

    if data_inicio_nova > data_fim_alvo:
        print(
            f"✅ {slugEstabelecimento}: nada novo para carregar "
            f"(até {data_fim_alvo.strftime('%d/%m/%Y')})."
        )
        return

    print(
        f"=== {slugEstabelecimento} — {ano}-{mes:02d} "
        f"(financeiro incremental, {DAYS_STEP} em {DAYS_STEP} dias até {data_fim_alvo}) ==="
    )

    sessao = doLogin()
    alteraEstabelecimento(sessao, idEstabelecimento)

    for inicio, fim in gerar_periodos(data_inicio_nova, data_fim_alvo, DAYS_STEP):
        print(
            f"⏺️ {slugEstabelecimento}: "
            f"{inicio.strftime('%d/%m/%Y')} → {fim.strftime('%d/%m/%Y')} [append]"
        )
        sessao = baixar_financeiro_periodo(sessao, idEstabelecimento, slugEstabelecimento, inicio, fim)
        time.sleep(2)  # pausa pequena entre janelas, ajuda o servidor


def main():
    global ANO, MES, TEVE_403

    # define ANO/MES
    if USE_CURRENT_MONTH:
        hoje_sp = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        if hoje_sp.day == 1:
            anterior = (hoje_sp.replace(day=1) - timedelta(days=1))
            ANO = anterior.year
            MES = anterior.month
        else:
            ANO = hoje_sp.year
            MES = hoje_sp.month

    print(f"\n##### Faturamento incremental — alvo {MES:02d}/{ANO} #####\n")

    # lista de estabelecimentos
    est_list = list(estabelecimentos.items())

    for bloco_ini in range(0, len(est_list), BLOCO_TAMANHO):
        bloco = est_list[bloco_ini : bloco_ini + BLOCO_TAMANHO]
        bloco_idx = bloco_ini // BLOCO_TAMANHO + 1
        print(f"\n🔹 Iniciando bloco {bloco_idx} (até {len(bloco)} estabelecimentos)...\n")

        for idx, (idEstabelecimento, (nome, slug)) in enumerate(bloco, start=1):
            print(f"\n>>> [{idx}/{len(bloco)}] Processando {slug} — {ANO}-{MES:02d} (faturamento incremental)")
            try:
                processar_estabelecimento(idEstabelecimento, slug, ANO, MES)
            except Exception as e:
                print(f"❌ Erro inesperado em {slug}: {e}")
            time.sleep(SLEEP_ENTRE_LOJAS)

        print(
            f"\n🔸 Bloco de {len(bloco)} estabelecimentos finalizado. "
            f"Pausando {SLEEP_ENTRE_BLOCOS} segundos para evitar 403…\n"
        )
        time.sleep(SLEEP_ENTRE_BLOCOS)

    if TEVE_403:
        print("\n⚠️ Faturamento finalizado, MAS houve respostas 403 em algumas faixas. Verifique o log acima.")
    else:
        print("\n🎉 Faturamento finalizado sem 403.")


if __name__ == "__main__":
    main()
