import blow as blow
import os
from datetime import date
hoje = date.today()
ano = int(hoje.strftime('%Y'))
# ano = 2020

for k,v in blow.estabelecimentos.items():
    idEstabelecimento = k
    nomeEstabelecimento = v[0]
    slugEstabelecimento = v[1]
    print("Atualizando relatórios para o estabelecimento {}".format(nomeEstabelecimento))

    print('Deletando os dados de ', nomeEstabelecimento)
    try:
        if not os.path.exists('demonstrativoresultado/batch/'+str(ano)):
            os.makedirs('demonstrativoresultado/batch/'+str(ano))
    except OSError:
        print('Não foi possivel criar o diretório')
    file = 'demonstrativoresultado/batch/{}/{}.csv'.format(ano, slugEstabelecimento)
    print(file)
    try:
        os.remove(file)
        print('Deletando arquivo .csv antes de iniciar a carga full')
    except:
        print('Não foi possível deletar o arquivo .csv')