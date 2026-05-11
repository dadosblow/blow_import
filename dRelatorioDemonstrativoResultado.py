import blow as blow
import os
from datetime import date, timedelta




# Faz login e abre sessão para baixar relatórios
s = blow.doLogin()

hoje = date.today()
ano = int(hoje.strftime('%Y'))

# ano = 2020
directory = 'demonstrativoresultado/batch/{}'.format(ano)

if not os.path.exists(directory):
    os.makedirs(directory)

for k,v in blow.estabelecimentos.items():
    idEstabelecimento = k
    nomeEstabelecimento = v[0]
    slugEstabelecimento = v[1]
    print("Atualizando relatórios para o estabelecimento {}".format(nomeEstabelecimento))
    estabelecimento = blow.alteraEstabelecimento(s, idEstabelecimento)
    print("Baixando relatório de demonstrativo resultado")
    relatorio = blow.DownloadRelatorioDemonstrativoResultado(s, idEstabelecimento, slugEstabelecimento)
    print(relatorio)