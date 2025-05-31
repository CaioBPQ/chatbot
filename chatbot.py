import os
import time
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import google.generativeai as genai

# Carrega variáveis de ambiente
load_dotenv()

# Inicializa cliente Gemini
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") 
if not GEMINI_API_KEY:
    print("Erro: A variável de ambiente GOOGLE_API_KEY não está configurada.")
    exit()

genai.configure(api_key=GEMINI_API_KEY)
print("API Key do Gemini configurada.")

# Inicializa o modelo Gemini
model = genai.GenerativeModel('gemini-1.5-flash') # Usando o modelo mais recente e rápido

# Configuração do WebDriver
driver = webdriver.Chrome()
driver.get("https://web.whatsapp.com")

print("Escaneie o QR Code com o celular e aperte ENTER aqui quando carregar.")
input()

contato = "amor" # Nome do contato no WhatsApp

# Busca o contato
try:
    search_box = driver.find_element(By.XPATH, '//div[contains(@contenteditable,"true") and @data-tab="3"]')
    search_box.click()
    search_box.send_keys(contato)
    search_box.send_keys(Keys.ENTER)
    time.sleep(3) # Espera o chat carregar
except Exception as e:
    print(f"Erro ao buscar o contato '{contato}': {e}")
    driver.quit()
    exit()

# Removida a função baixar_audio e transcrever_audio, pois não serão usadas sem Whisper ou outra API de transcrição.
# Se você quiser que o bot tente processar áudios com Gemini como entrada multimodal,
# esta parte precisaria de uma implementação SIGNIFICATIVAMENTE mais complexa,
# incluindo conversão de formato de áudio (ogg para mp3/wav/flac) e manipulação de objetos Media no Gemini.

def get_last_message_and_type():
    """Pega a última mensagem recebida e identifica o tipo (texto ou áudio)"""
    try:
        # Espera que pelo menos uma mensagem recebida (message-in) apareça
        # Isso ajuda a garantir que o bot não tente ler antes de uma mensagem realmente chegar.
        # Aumentei o tempo de espera para dar mais chance.
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "message-in")]'))
        )
        
        # Agora sim, pegamos TODAS as mensagens recebidas
        mensagens_recebidas = driver.find_elements(By.XPATH, '//div[contains(@class, "message-in")]')

        if not mensagens_recebidas:
            # Não há mensagens recebidas na tela
            return "", "texto", "" # Retorna (mensagem, tipo, timestamp) vazio

        ultima_recebida = mensagens_recebidas[-1]
        
        # Espera que o elemento copyable-text esteja presente DENTRO da última mensagem recebida
        # Isso é crucial para o timestamp e o texto.
        pre_plain_text_element = WebDriverWait(ultima_recebida, 5).until(
            EC.presence_of_element_located((By.XPATH, './/div[contains(@class, "copyable-text")]'))
        )
        
        pre_plain_text = pre_plain_text_element.get_attribute("data-pre-plain-text")
        
        # Extrai o timestamp único (parte entre colchetes)
        timestamp = pre_plain_text.split("]")[0].strip() + "]" if "]" in pre_plain_text else ""


        # Verifica se é áudio
        # Este bloco precisa ser robusto o suficiente para não falhar completamente a função.
        msg_type = "texto"
        try:
            # Tenta encontrar um elemento que indique áudio dentro da mensagem recebida
            # O WhatsApp Web muda bastante. Tente esses seletores:
            # Botão de play do áudio:
            audio_play_button = ultima_recebida.find_elements(By.XPATH, './/button[@aria-label="Reproduzir mensagem de áudio"] | .//div[@data-testid="audio-playback-button"]')
            if audio_play_button: # Se encontrou o botão de play, é áudio
                msg_type = "audio"
        except Exception as audio_e:
            # print(f"DEBUG: Não é áudio ou erro ao detectar áudio: {audio_e}") # Para depuração
            pass # Continua como texto se não for áudio

        # Pega o conteúdo da mensagem (texto ou placeholder de áudio)
        text_content = ""
        if msg_type == "audio":
            text_content = "ÁUDIO_DETECTADO"
        else:
            try:
                # Prioriza o span com o texto da mensagem
                text_span_element = WebDriverWait(ultima_recebida, 2).until(
                    EC.presence_of_element_located((By.XPATH, './/div[@class="_akbu"]/span[@dir="ltr"]'))
                )
                text_content = text_span_element.text
            except:
                # Como fallback, tenta pegar o texto do copyable-text e remover o prefixo
                try:
                    full_text_from_copyable = pre_plain_text_element.text 
                    if pre_plain_text and full_text_from_copyable.startswith(pre_plain_text):
                        text_content = full_text_from_copyable[len(pre_plain_text):].strip()
                    else:
                        text_content = full_text_from_copyable 
                except:
                    text_content = "" # Se tudo falhar, retorna vazio


        return text_content.strip(), msg_type, timestamp
        
    except Exception as e:
        # Se ocorrer um erro em alguma parte da detecção (ex: elemento não encontrado),
        # retorne valores vazios para indicar que nenhuma nova mensagem foi processada.
        # Isso evita que o bot trave por erros de Selenium quando não há mensagens ou a estrutura muda.
        # print(f"Erro ao obter mensagem: {e}") # Descomente para depurar se o bot parar de funcionar
        return "", "texto", "" # Retorna vazio, não causa resposta

# Variável global para armazenar o histórico de mensagens
historico_conversa = []

def configurar_historico_inicial(mensagem_recebida):
    """
    Configura o histórico de conversa com o prompt de sistema
    e a primeira mensagem do usuário.
    """
    global historico_conversa
    historico_conversa = [
        {"role": "user", "parts": [
            {"text": (
                "Você é o Caio, namorado da Isa ou Isabela. "
                "Fala de forma informal, misturando brincadeira pesada e carinhosa: "
                "ofensas zoeiras mas so se ela tiver na brincadeira"
                "palavrões com indignação como 'pqp olha que bosta', "
                "mas nunca grosseiro, sempre com humor e carinho. "
                "Quando ela fala que vai dormir, responde com muito amor, tipo 'te amo muito meu amor', "
                "'dorme bem vida', 'descansa princesa', 'te amo muito muito muito benzinho'. "
                "Se ela reclama ou fala algo ruim, responde com indignação engraçada."
                "Evite ser completamente meloso seja carinhoso e engraçado, mas nunca muito meloso ou sério demais."
                "Nunca use emojis, apenas texto."
                "Quase nao usar virgulas, mas sempre usar interrogação quando necessário."
                "Use sempre palavras de baixo calão, mas nunca de forma agressiva, sempre com humor."
                "Baseie suas respostas no histórico de mensagens, mas nunca repita o que ela disse."
                "Se ela citar que vc esta estranho ou algo do genero, fala que ela descobriu que ela tava falando com chat gpt esse tempo todo"
                "e da um KKKKKKKKKKKKKKKKKKKKKKKKKKKKK imenso na conversa."
                "NÃO SEJA muito cafajeste, converse natural sem chamar de safada o seja um pouco romantico mas nem tanto"
                "nao use virgulas, so se for muito necessário, em caso que precisa para a interpretação."

            )}
        ]},
        # Exemplos de turno de conversa para reforçar o estilo (Few-shot prompting)
        {"role": "user", "parts": [{"text": "kkkkkk que bicha feiaaaaaa"}]},
        {"role": "model", "parts": [{"text": "vc é doida, feia, fedida, mas eu amo vc assim mesmo"}]},
        {"role": "user", "parts": [{"text": "Crll, que bosta mesmo"}]},
        {"role": "model", "parts": [{"text": "Pqp, olha que bosta esse dia."}]},
        {"role": "user", "parts": [{"text": "Vou dormir."}]},
        {"role": "model", "parts": [{"text": "Te amo muito meu amor, dorme bem vida, descansaaaa, princesa"}]},
        # Adiciona a primeira mensagem real do usuário
        {"role": "user", "parts": [{"text": mensagem_recebida}]}
    ]

def responder_com_gemini(mensagem_recebida):
    """Gera resposta usando Gemini"""
    global historico_conversa

    # Se o histórico estiver vazio, inicialize-o com o prompt de sistema e a primeira mensagem
    if not historico_conversa:
        configurar_historico_inicial(mensagem_recebida)
    else:
        # Adiciona a nova mensagem do usuário ao histórico
        historico_conversa.append({"role": "user", "parts": [{"text": mensagem_recebida}]})

    try:
        # Envia o histórico completo para o Gemini
        response = model.generate_content(
            historico_conversa,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=150,
                temperature=0.8,
                top_p=1,
                top_k=1
            )
        )
        
        # A resposta do Gemini pode vir em partes, então juntamos
        resposta_texto = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text'):
                resposta_texto += part.text

        # Adiciona a resposta do modelo ao histórico para a próxima iteração
        historico_conversa.append({"role": "model", "parts": [{"text": resposta_texto}]})
        
        return resposta_texto
        
    except Exception as e:
        print(f"Erro ao gerar resposta com Gemini: {e}")
        # Em caso de erro, talvez seja bom limpar o histórico ou encurtá-lo para evitar erros repetidos
        if len(historico_conversa) > 5: # Mantém um histórico pequeno em caso de erro
            historico_conversa = historico_conversa[-5:] 
        return "ih caralho deu errado, ignora essa porra kkkkkkkk"


def enviar_mensagem(texto):
    """Envia mensagem no WhatsApp"""
    try:
        # Seletor para a caixa de texto do WhatsApp Web (pode variar)
        caixa = driver.find_element(By.CSS_SELECTOR, 'div[contenteditable="true"][data-tab="10"]')
        caixa.click()
        # Apaga tudo antes de digitar (CTRL+A + BACKSPACE) para evitar concatenar mensagens
        caixa.send_keys(Keys.CONTROL + "a")
        caixa.send_keys(Keys.BACKSPACE)
        caixa.send_keys(texto)
        caixa.send_keys(Keys.ENTER)
        return True
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
        return False


# No loop principal, onde você tem:
# ultima_mensagem_timestamp = "" 

print("Bot iniciado! Monitorando mensagens...")

# Variável para armazenar o timestamp da ÚLTIMA mensagem *processada* pelo bot
last_processed_message_timestamp = "" 
contador_erro = 0

while True:
    try:
        msg_content, msg_type, msg_timestamp = get_last_message_and_type()
        
        # Só processa se houver uma nova mensagem recebida (diferente da última que processamos)
        if msg_content and msg_timestamp and msg_timestamp != last_processed_message_timestamp:
            print(f"\n{'='*50}")
            
            if msg_type == "audio":
                print("📢 Mensagem dela: [Áudio recebido]")
                resposta = "Não consegui ouvir audio porra, escreve ai kkkk"
            else:
                print(f"💬 Mensagem dela: {msg_content}")
                resposta = responder_com_gemini(msg_content)

            print(f"🤖 Respondendo: {resposta}")
            
            if enviar_mensagem(resposta):
                last_processed_message_timestamp = msg_timestamp # Atualiza o timestamp da última mensagem processada
                contador_erro = 0
            else:
                print("❌ Falha ao enviar mensagem")
                
        time.sleep(3) # Intervalo para verificar novas mensagens
        
    except Exception as e:
        contador_erro += 1
        print(f"❌ Erro geral no loop #{contador_erro}: {e}")
        
        if contador_erro > 10:
            print("🛑 Muitos erros consecutivos. Parando o bot.")
            break
            
        time.sleep(5) 

# Cleanup
driver.quit()
print("Bot finalizado.")