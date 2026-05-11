import blow_p2 as blow
import os
import time

# ===================== CONFIG =====================
BLOCK_SIZE = 10              # quantas lojas por bloco
SLEEP_BETWEEN_BLOCKS = 300   # segundos de pausa entre blocos (5 min)
SLEEP_BETWEEN_STORES = 2     # pausa leve entre lojas (segundos)

MAX_RETRIES_PER_STORE = 3    # quantas vezes tentar a mesma loja se der erro
SLEEP_RETRY_STORE = 30       # pausa entre tentativas da MESMA loja (segundos)
# ==================================================

directory = "profissionais"

if not os.path.exists(directory):
    os.makedirs(directory)

# fixa a lista de estabelecimentos (na ordem do dict)
estabs = list(blow.estabelecimentos.items())
total = len(estabs)

for idx, (idEstabelecimento, (nomeEstabelecimento, slugEstabelecimento)) in enumerate(estabs, start=1):
    print(f">>> [{idx}/{total}] Atualizando relatórios para o estabelecimento {nomeEstabelecimento} ({slugEstabelecimento})")

    sucesso = False

    for tentativa in range(1, MAX_RETRIES_PER_STORE + 1):
        print(f"🔄 Tentativa {tentativa} para {slugEstabelecimento}")

        # 🔐 login novo a cada tentativa
        sessao = blow.doLogin()

        # garante que estamos no estabelecimento correto
        sessao_estab = blow.alteraEstabelecimento(sessao, idEstabelecimento)

        print("Baixando relatório de profissionais (ativos + inativos)...")
        try:
            relatorio = blow.downloadRelatorioProfissionais(sessao_estab, idEstabelecimento, slugEstabelecimento)
        except Exception as e:
            print(f"⚠️ Erro inesperado em {slugEstabelecimento}: {e}")
            relatorio = None

        print(relatorio)
        print()

        # se veio aquela mensagem de erro de JSON/HTML, vamos tentar de novo
        if isinstance(relatorio, str) and "Resposta não JSON" in relatorio:
            print(
                f"⚠️ Download de profissionais para {slugEstabelecimento} retornou erro. "
                f"Aguardando {SLEEP_RETRY_STORE}s antes de tentar novamente..."
            )
            time.sleep(SLEEP_RETRY_STORE)
            continue

        # se chegou aqui, consideramos que deu certo
        sucesso = True

        # fecha a sessão desta loja
        try:
            sessao.close()
        except Exception:
            pass

        break  # sai do loop de tentativas

    if not sucesso:
        print(
            f"❌ Não foi possível baixar profissionais para {slugEstabelecimento} "
            f"após {MAX_RETRIES_PER_STORE} tentativas."
        )

    # pausa leve entre lojas
    if idx < total:
        time.sleep(SLEEP_BETWEEN_STORES)

    # fim de bloco → pausa maior
    if idx % BLOCK_SIZE == 0 and idx < total:
        print(
            f"🔹 Bloco de {BLOCK_SIZE} estabelecimentos finalizado "
            f"({idx}/{total}). Pausando {SLEEP_BETWEEN_BLOCKS} segundos para evitar 403…"
        )
        time.sleep(SLEEP_BETWEEN_BLOCKS)

print("✅ Processamento de profissionais finalizado para todos os estabelecimentos.")
