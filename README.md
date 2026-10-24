# teclavoz

Teste de digitação no terminal, estilo 10fastfingers, que **fala cada palavra** que você acerta.

- Idiomas: PT-BR e EN · Categorias: dia a dia (~230 palavras), TI (~400) ou misto
- Voz neural offline com [Piper](https://github.com/OHF-Voice/piper1-gpl) (fallback: `espeak-ng`)
- Usa as cores do tema atual do Omarchy e acompanha a troca de tema ao vivo

## Modos

- **eco** — você lê e digita; a palavra é falada quando você acerta.
- **ditado** — as palavras ficam escondidas; cada uma é falada e você digita de ouvido.
  Se errar, a palavra certa aparece sublinhada. Recordes são separados por modo.

Troque com **F7** ou digitando `/mode` + Enter no campo (`/mode eco`, `/mode ditado`).

## Vozes

Cada idioma tem a sua voz, escolhida com F9 ou `/voz`. A voz nova é baixada (~60 MB) na
primeira vez; até terminar, a anterior continua falando.

- PT-BR: faber (padrão), cadu, jeff, edresson
- EN: lessac (padrão), amy, ryan, kristin, joe, john, hfc_female, hfc_male, alba (GB), alan (GB)
- Qualquer outra voz do Piper do mesmo idioma também funciona pelo nome completo.

## Instalar

    ./install.sh

## Teclas

| Tecla  | Ação                                  |
|--------|---------------------------------------|
| espaço | confirma a palavra                    |
| F2     | idioma (PT-BR / EN)                   |
| F3     | categoria (dia a dia / TI / misto)    |
| F4     | duração (15 / 30 / 60 / 120 s)        |
| F5     | liga/desliga a voz                    |
| F6     | exigir ou ignorar acentos             |
| F7     | modo (eco / ditado)                   |
| F8     | repetir a palavra (ditado)            |
| F9     | trocar a voz do idioma atual          |
| F10    | velocidade da voz: 1.0 → 1.2 → 1.35 → 1.5 → 1.7 → 2.0 |
| Esc    | reiniciar                             |
| Ctrl+Q | sair                                  |

Comandos: digite `/` no campo e um menu abre com todos eles (filtra conforme você digita).
↑/↓ escolhe, Enter executa, Tab completa, Esc fecha. Também dá para digitar direto: `/mode [eco|ditado]`, `/repetir` (ou `/r`),
`/voz` (lista as vozes), `/voz <nº|nome>` (ex.: `/voz 2`, `/voz cadu`, `/voz en_US-ryan-high`),
`/velocidade <0.8–2.0>` (ou `/vel`) — ritmo da voz; 1.0 é o natural, maior é mais lento (padrão 1.35).

## Arquivos

- Palavras: `teclavoz/data/*.txt` (uma por linha; edite à vontade)
- Vozes: `~/.local/share/teclavoz/voices/`
- Cache de áudio: `~/.cache/teclavoz/`
- Configurações e recordes: `~/.local/share/teclavoz/{settings,records}.json`
- Tema lido de: `~/.local/state/omarchy/current/theme/colors.toml`
