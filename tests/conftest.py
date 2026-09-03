"""Isola os testes do .env da máquina.

Os módulos chamam load_dotenv() na importação, o que faria a suíte passar ou
falhar conforme o .env local — que nem é versionado. Aqui load_dotenv vira
no-op antes de qualquer módulo de teste ser importado, então os testes só
enxergam as variáveis que eles mesmos definem.
"""

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False
