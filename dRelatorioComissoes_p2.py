from blow_p2 import (
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
import requests  # ⭐ novo: vamos usar requests direto

# ========================
# CONFIGURAÇÕES
# ========================
USE_CURRENT_MONTH = True    # True = sempre mês corrente; False = usa ANO/MES fixos abaixo
ANO = 2025                  # usado se USE_CURRENT_MONTH = False
MES = 11                    # usado se USE_CURRENT_MONTH = False

DAYS_STEP = 5               # tamanho da janela em dias
BLOCO_TAMANHO = 10          # quantos estabelecimentos por bloco
SLEEP_ENTRE_BLOCOS = 180    # segundos entre blocos
SLEEP_ENTRE_LOJAS = 1       # segundos entre lojas

MAX_TENTATIVAS_FAIXA = 3    # quantas vezes tentar a MESMA faixa ao pegar 403

# flag global para sabermos se teve 403 em algum momento
TEVE_403 = False


def get_last_loaded_date(tipo: str, ano: int, mes: int, slug: str) -> date | None:
    """
    Lê o CSV existente (tipo/batch/ano/mes/slug.csv) e retorna a última data carregada
    usando especificamente a coluna 'Atendimento/Venda'.
    """
    path = f"{tipo}/batch/{ano}/{mes:02d}/{slug}.csv"
    if not os.path.isfile(path):
        return None

    try:
        df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    except Exception as e:
        print(f"⚠️ Não consegui ler {path} ({e}).")
        return None

    if "Atendimento/Venda" not in df.columns:
        print(f"⚠️ CSV não contém a coluna 'Atendimento/Venda'. Não é possível fazer incremental.")
        return None

    try:
        dt_series = pd.to_datetime(df["Atendimento/Venda"], dayfirst=True, errors="coerce").dropna()
    except Exception as e:
        print(f"⚠️ Erro ao converter datas da coluna Atendimento/Venda ({e}).")
        return None

    if dt_series.empty:
        return None

    return dt_series.max().date()


def baixar_comissoes_periodo(
    sessao,
    idEstabelecimento: str,
    slugEstabelecimento: str,
    data_inicio: date,
    data_fim: date,
):
    """
    Baixa relatório de COMISSÕES para [data_inicio, data_fim]
    e faz append no CSV do mês.

    👉 Se der 403/HTML, reloga e tenta novamente a MESMA faixa,
       até MAX_TENTATIVAS_FAIXA vezes.

    Retorna sempre a sessão (que pode ter sido recriada).
    """
    global TEVE_403

    tipo = "comissoes"
    ano = data_inicio.year
    mes = data_inicio.month

    dataInicio_str = data_inicio.strftime("%d/%m/%Y")
    dataFim_str = data_fim.strftime("%d/%m/%Y")

    for tentativa in range(1, MAX_TENTATIVAS_FAIXA + 1):
        print(f"⬇️ Comissões {slugEstabelecimento}: {dataInicio_str} → {dataFim_str} (tentativa {tentativa})")

        url = "https://www.trinks.com/BackOffice/Download/ExportarComissoes"
        headers = {
            "id-estabelecimento-autenticado": idEstabelecimento,
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.trinks.com/BackOffice/Relatorios/Comissoes",
        }

        data = {
            "TipoData": "1",
            "DataInicio": dataInicio_str,
            "DataFim": dataFim_str,
            "CodigoProfissional": "-1",
            "TipoItemPago": "0",
            "ExibirEstornos": "false",
            "IdRelacaoProfissional": "0",
        }

        try:
            r = sessao.post(url, headers=headers, data=data, timeout=(10, 90))
        except requests.RequestException as e:
            print(f"⚠️ Erro de rede ao chamar ExportarComissoes: {e}")
            time.sleep(2)
            continue

        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct or r.status_code == 403:
            # sessão provavelmente bloqueada/expirada
            TEVE_403 = True
            print("⚠️ Recebi HTML (provável sessão expirada ou bloqueada). Tentando relogar…")

            try:
                sessao.close()
            except:
                pass

            # novo login + troca de estabelecimento
            sessao = doLogin()
            alteraEstabelecimento(sessao, idEstabelecimento)
            time.sleep(2)
            # volta para o início do loop: tenta MESMA faixa de novo
            continue

        try:
            jsonResponse = json.loads(r.content)
        except json.JSONDecodeError:
            print(
                f"⚠️ Resposta não é JSON para {dataInicio_str}..{dataFim_str}. "
                f"Status {r.status_code}. Trecho: {r.text[:200]}"
            )
            # se não for 403, não adianta relogar infinitamente; sai da faixa
            return sessao

        if "Dados" not in jsonResponse or not jsonResponse["Dados"]:
            print(f"Sem dados para {dataInicio_str}..{dataFim_str}")
            return sessao

        dados = jsonResponse["Dados"]
        urlDownload = (
            "https://www.trinks.com/BackOffice/Download/DownloadCsvRelatorios"
            f"?guidParaBuscarArquivoNaSessao={dados}"
        )

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
    inicio = data_inicio
    while inicio <= data_fim:
        fim = min(inicio + timedelta(days=step_dias - 1), data_fim)
        yield inicio, fim
        inicio = fim + timedelta(days=1)


def processar_estabelecimento(
    sessao,
    idEstabelecimento: str,
    slugEstabelecimento: str,
    ano: int,
    mes: int,
):
    TZ = ZoneInfo("America/Sao_Paulo")
    hoje_sp = datetime.now(TZ).date()

    primeiro_dia_mes = date(ano, mes, 1)
    ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)

    if ano == hoje_sp.year and mes == hoje_sp.month:
        if hoje_sp.day == 1:
            print(f"📅 {slugEstabelecimento}: hoje é dia 01, nada para carregar ainda do mês {mes:02d}/{ano}.")
            return
        data_fim_alvo = min(hoje_sp - timedelta(days=1), ultimo_dia_mes)
    else:
        data_fim_alvo = ultimo_dia_mes

    ultima_data = get_last_loaded_date("comissoes", ano, mes, slugEstabelecimento)

    if ultima_data is None:
        data_inicio_nova = primeiro_dia_mes
        print(
            f"📂 {slugEstabelecimento}: arquivo ainda não existe ou sem data válida. "
            f"Vai carregar desde {data_inicio_nova.strftime('%d/%m/%Y')}."
        )
    else:
        data_inicio_nova = ultima_data + timedelta(days=1)
        print(
            f"📂 {slugEstabelecimento}: última data = {ultima_data.strftime('%Y-%m-%d')}, "
            f"carregando de {data_inicio_nova.strftime('%Y-%m-%d')}"
        )

    if data_inicio_nova > data_fim_alvo:
        print(
            f"✅ {slugEstabelecimento}: nada novo para carregar "
            f"(até {data_fim_alvo.strftime('%d/%m/%Y')})."
        )
        return

    print(
        f"=== {slugEstabelecimento} — {ano}-{mes:02d} "
        f"(comissões incremental, {DAYS_STEP} em {DAYS_STEP} dias até {data_fim_alvo}) ==="
    )

    alteraEstabelecimento(sessao, idEstabelecimento)

    for inicio, fim in gerar_periodos(data_inicio_nova, data_fim_alvo, DAYS_STEP):
        print(
            f"⏺️ {slugEstabelecimento}: "
            f"{inicio.strftime('%d/%m/%Y')} → {fim.strftime('%d/%m/%Y')} [append]"
        )
        sessao = baixar_comissoes_periodo(sessao, idEstabelecimento, slugEstabelecimento, inicio, fim)
        time.sleep(2)


def main():
    global ANO, MES, TEVE_403

    if USE_CURRENT_MONTH:
        hoje_sp = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        if hoje_sp.day == 1:
            anterior = (hoje_sp.replace(day=1) - timedelta(days=1))
            ANO = anterior.year
            MES = anterior.month
        else:
            ANO = hoje_sp.year
            MES = hoje_sp.month

    print(f"\n##### Comissões incremental — alvo {MES:02d}/{ANO} #####\n")

    est_list = list(estabelecimentos.items())
    total = len(est_list)

    for bloco_ini in range(0, len(est_list), BLOCO_TAMANHO):
        bloco = est_list[bloco_ini : bloco_ini + BLOCO_TAMANHO]
        bloco_idx = bloco_ini // BLOCO_TAMANHO + 1
        print(f"\n🔹 Iniciando BLOCO {bloco_idx} (até {len(bloco)} estabelecimentos)...\n")

        # sessão nova para CADA BLOCO
        sessao = doLogin()

        for idx, (idEstabelecimento, (nome, slug)) in enumerate(bloco, start=1):
            print(f"\n>>> [{idx}/{len(bloco)}] Processando {slug} — {ANO}-{MES:02d} (comissões incremental)")
            try:
                processar_estabelecimento(sessao, idEstabelecimento, slug, ANO, MES)
            except Exception as e:
                print(f"❌ Erro inesperado em {slug}: {e}")

            time.sleep(SLEEP_ENTRE_LOJAS)

        print(
            f"\n🔸 Bloco de {len(bloco)} estabelecimentos finalizado. "
            f"Pausando {SLEEP_ENTRE_BLOCOS} segundos para evitar 403…\n"
        )

        try:
            sessao.close()
        except:
            pass
        time.sleep(SLEEP_ENTRE_BLOCOS)

    if TEVE_403:
        print("\n⚠️ Processamento finalizado, MAS houve respostas 403 em algumas faixas. Verifique o log acima.")
    else:
        print("\n🎉 Processamento finalizado sem 403.")


if __name__ == "__main__":
    main()
