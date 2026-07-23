import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from dotenv import load_dotenv
from flask import Flask
import threading
import asyncio 
from discord.ui import Modal, TextInput
from discord import TextStyle, Color, Embed, Interaction
import difflib
import unicodedata
from groq import Groq


# Cargar variables de entorno
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
# Inicializar bot de Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="z6 ", intents=intents, case_insensitive=True)



# Inicializar Flask
app = Flask(__name__)

# Archivo de respuestas automáticas
RESPUESTAS_FILE = 'respuestas_automáticas.json'

def cargar_respuestas():
    """Carga las respuestas automáticas desde el archivo JSON"""
    if os.path.exists(RESPUESTAS_FILE):
        with open(RESPUESTAS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def guardar_respuestas(respuestas):
    """Guarda las respuestas automáticas en el archivo JSON"""
    with open(RESPUESTAS_FILE, 'w', encoding='utf-8') as f:
        json.dump(respuestas, f, indent=4, ensure_ascii=False)

# Mapeo de colores
COLORES = {
    "verde": discord.Color.green(),
    "amarillo": discord.Color.gold(),
    "rojo": discord.Color.red()
}

# ==================== EVENTOS DEL BOT ====================

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} comandos sincronizados')
    except Exception as e:
        print(f'❌ Error al sincronizar comandos: {e}')


# Carga los datos AFK al inicio de tu archivo
AFK_FILE = "afk.json"

def cargar_afk():
    if os.path.exists(AFK_FILE):
        with open(AFK_FILE, "r", encoding="utf-8") as f:
            try:
                return {int(k): v for k, v in json.load(f).items()}
            except:
                return {}
    return {}

def guardar_afk(data):
    with open(AFK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

afk_users = cargar_afk()

# ÚNICO EVENTO ON_MESSAGE
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # --- 1. SI EL USUARIO AFK ESCRIBE, SE LE QUITA EL ESTADO ---
    if message.author.id in afk_users:
        del afk_users[message.author.id]
        guardar_afk(afk_users)
        try:
            await message.channel.send(f"🎉 ¡Bienvenido de vuelta, {message.author.mention}! Ya te he retirado el estado AFK. 🚀")
        except discord.HTTPException:
            pass

    # --- 2. COMANDO AFK (Usa EMBED y REPLY) ---
    contenido_lower = message.content.lower()
    if contenido_lower.startswith("z6 afk"):
        partes = message.content.split(" ", 2)
        razon = partes[2] if len(partes) > 2 else "Sin razón especificada"
        
        afk_users[message.author.id] = razon
        guardar_afk(afk_users)
        
        # Creamos el Embed decorado para la activación
        embed_afk = discord.Embed(
            title="💤 ¡Modo AFK Activado!",
            description=f"Te has puesto ausente correctamente.",
            color=discord.Color.orange()
        )
        embed_afk.add_field(name="📌 Razón", value=razon, inline=False)
        embed_afk.set_footer(text="⚡ Se te quitará el estado en cuanto escribas un mensaje.")
        
        await message.reply(embed=embed_afk)
        return

    # --- 3. DETECTAR MENCIONES Y CONEXIONES (Mensaje normal con emojis) ---
    if message.mentions:
        for user in message.mentions:
            if user.id in afk_users:
                razon = afk_users[user.id]
                
                accion_extra = None
                for activity in user.activities:
                    if isinstance(activity, discord.Spotify):
                        accion_extra = f"🎧 Escuchando **{activity.title}** de *{', '.join(activity.artists)}* en Spotify"
                        break
                    elif activity.type == discord.ActivityType.playing:
                        accion_extra = f"🎮 Jugando a **{activity.name}**"
                        break
                    elif activity.type == discord.ActivityType.streaming:
                        accion_extra = f"📺 Transmitiendo en directo: **{activity.name}**"
                        break
                    elif activity.type == discord.ActivityType.listening:
                        accion_extra = f"🎵 Escuchando **{activity.name}**"
                        break
                    elif activity.name:
                        accion_extra = f"✨ Actividad: **{activity.name}**"
                        break

                # Mensaje normal con emojis para las menciones
                texto_respuesta = f"⚠️ **{user.mention} se encuentra AFK en este momento.**\n> 📌 **Razón:** {razon}"
                if accion_extra:
                    texto_respuesta += f"\n> {accion_extra}"

                await message.reply(texto_respuesta)

    # --- 4. TUS RESPUESTAS AUTOMÁTICAS ---
    import json
    import os
    archivo = "respuestas_automáticas.json"

    if os.path.exists(archivo):
        with open(archivo, "r", encoding="utf-8") as f:
            try:
                datos = json.load(f)
            except json.JSONDecodeError:
                datos = {}

        guild_id = str(message.guild.id)
        if guild_id in datos:
            activador = message.content.strip()
            if activador in datos[guild_id]:
                mensaje_respuesta = datos[guild_id][activador]
                await message.channel.send(mensaje_respuesta)

    
    # --- 5. COMANDO INTELIGENTE (MENCIÓN + REPLY + IMÁGENES + HISTORIAL DE 3 MENSAJES + 1 PALABRA DE HUMOR) ---
    if bot.user in message.mentions:
        pregunta = message.content
        for mention in message.mentions:
            pregunta = pregunta.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "").strip()

        contexto_historial = []
        imagen_url = None
        mensaje_actual = message

        # Rastrear hacia atrás el hilo de replies hasta un máximo de 3 mensajes previos
        for _ in range(3):
            if mensaje_actual.reference and mensaje_actual.reference.message_id:
                try:
                    mensaje_ref = await message.channel.fetch_message(mensaje_actual.reference.message_id)
                    if mensaje_ref:
                        rol_ref = "assistant" if mensaje_ref.author == bot.user else "user"
                        autor_nombre = mensaje_ref.author.display_name
                        contenido_ref = f"[{autor_nombre}]: {mensaje_ref.content}" if mensaje_ref.content else f"[{autor_nombre} envió contenido multimedia]"
                        
                        # Insertar al inicio para mantener el orden cronológico correcto
                        contexto_historial.insert(0, {
                            "role": rol_ref, 
                            "content": contenido_ref
                        })

                        # Capturar imagen si el mensaje del hilo tiene adjuntos
                        if not imagen_url and mensaje_ref.attachments:
                            for attachment in mensaje_ref.attachments:
                                if attachment.content_type and "image" in attachment.content_type:
                                    imagen_url = attachment.url
                                    break

                        mensaje_actual = mensaje_ref
                    else:
                        break
                except Exception as e:
                    print(f"Error al obtener mensaje del historial: {e}")
                    break
            else:
                break

        # Revisar si el mensaje actual que menciona al bot trae una imagen adjunta
        if not imagen_url and message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and "image" in attachment.content_type:
                    imagen_url = attachment.url
                    break

        async with message.channel.typing():
            try:
                system_prompt = (
                    "Eres un asistente directo y útil, pero tienes una personalidad sutilmente relajada. "
                    "REGLA DE ORO DE HUMOR: En momentos especiales de la conversación, incluye OBLIGATORIAMENTE **exactamente una sola palabra** de humor de internet (por ejemplo: 'basado', 'aura', 'xd', 'god', 'cenizo' o similares) integrada de forma natural en toda la respuesta. Nunca uses más de una palabra de este tipo por mensaje. "
                    "REGLA ABSOLUTA DE EXTENSIÓN: Tu respuesta NO PUEDE superar las 75 palabras bajo ninguna circunstancia."
                )

                user_content = []
                if imagen_url:
                    user_content.append({"type": "image_url", "image_url": {"url": imagen_url}})
                
                texto_final = pregunta if pregunta else "¿Qué onda con esto?"
                user_content.append({"type": "text", "text": texto_final})

                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(contexto_historial)
                messages.append({"role": "user", "content": user_content})

                completion = client.chat.completions.create(
                    model="meta-llama/llama-4-maverick-17b-128e-instruct",
                    messages=messages,
                    max_tokens=120,
                    temperature=0.7,
                )

                reply_text = completion.choices[0].message.content or "xd."
                await message.reply(reply_text)

            except Exception as e:
                print(f"Error con Groq (Vision): {e}")
                await message.reply(f"Me quedé sin saldo. Error: `{str(e)}`")
        
        return
                
        
        
    # --- 6. PROCESAR COMANDOS TRADICIONALES ---
    await bot.process_commands(message)

# ==================== COMANDO /mensaje ====================

# 1. Definir el formulario (Modal)
class FormularioMensaje(Modal, title='Enviar Mensaje Personalizado'):
    texto = TextInput(label='Mensaje (fuera del embed)', style=TextStyle.paragraph, required=True)
    embed_desc = TextInput(label='Contenido del Embed (opcional)', style=TextStyle.paragraph, required=False)
    color_input = TextInput(label='Color (amarillo, azul o rojo)', style=TextStyle.short, required=False, placeholder="amarillo, azul o rojo")

    async def on_submit(self, interaction: Interaction):
        # Mapeo de colores
        colores = {
            "amarillo": Color.yellow(),
            "azul": Color.blue(),
            "rojo": Color.red()
        }
        
        # Obtener el color seleccionado (por defecto azul si no se encuentra)
        color = colores.get(self.color_input.value.lower(), Color.blue())
        
        # Preparar el embed si se ingresó contenido
        embed = None
        if self.embed_desc.value:
            embed = Embed(description=self.embed_desc.value, color=color)
            
        # El bot publica el mensaje en el canal (aparece a nombre del bot)
        await interaction.channel.send(
            content=self.texto.value, 
            embed=embed
        )
        
        # Confirmación privada (ephemeral) para quien usó el comando
        await interaction.response.send_message(
            content="✅ Mensaje enviado correctamente.", 
            ephemeral=True
        )

# 2. Comando Slash con restricción de administrador
@bot.tree.command(name="mensaje_o_embed", description="Envía un mensaje tipo formulario")
@app_commands.checks.has_permissions(administrator=True)
async def mensaje_o_embed(interaction: Interaction):
    await interaction.response.send_modal(FormularioMensaje())

# 3. Manejador de error en caso de que alguien sin permisos intente usarlo
@mensaje_o_embed.error
async def mensaje_o_embed_error(interaction: Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            content="❌ No tienes permisos de administrador para usar este comando.", 
            ephemeral=True
        )
        
# ==================== COMANDO /savetexto ====================

# 1. El Formulario (Modal)
class ModalGuardarTexto(discord.ui.Modal, title="Guardar Nueva Respuesta"):
    activador = discord.ui.TextInput(
        label="Activador (palabra clave)",
        placeholder="Ej: !hola o hola",
        style=discord.TextStyle.short,
        required=True
    )
    
    mensaje = discord.ui.TextInput(
        label="Mensaje a guardar",
        placeholder="Escribe aquí el texto que responderá el bot...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        act = self.activador.value
        msg = self.mensaje.value
        guild_id = str(interaction.guild.id)

        import json
        import os

        archivo = "respuestas_automáticas.json"
        
        # Cargar datos actuales o crear estructura vacía
        if os.path.exists(archivo):
            with open(archivo, "r", encoding="utf-8") as f:
                try:
                    datos = json.load(f)
                except json.JSONDecodeError:
                    datos = {}
        else:
            datos = {}

        # Guardar / Actualizar por servidor (guild_id)
        if guild_id not in datos:
            datos[guild_id] = {}
        
        datos[guild_id][act] = msg

        # Escribir de vuelta al archivo JSON
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)

        await interaction.response.send_message(
            f"¡Respuesta automática guardada exitosamente!\n> **Activador:** `{act}`\n> **Mensaje:** {msg}",
            ephemeral=True
        )


# 2. El Comando Slash con restricción de Administrador
@bot.tree.command(name="savetexto", description="Guarda un texto personalizado asociado a un activador")
@app_commands.checks.has_permissions(administrator=True)
async def savetexto(interaction: discord.Interaction):
    modal = ModalGuardarTexto()
    await interaction.response.send_modal(modal)

# 3. Manejador de errores por si alguien sin permisos intenta usarlo
@savetexto.error
async def savetexto_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "❌ No tienes permisos de **Administrador** para usar este comando.", 
            ephemeral=True
        )
        


@bot.tree.command(name="pregunta", description="Inicia una ronda de preguntas (Moderadores)")
@app_commands.checks.has_permissions(manage_messages=True)
async def pregunta(
    interaction: discord.Interaction, 
    pregunta: str, 
    respuesta: str, 
    tiempo_segundos: int, 
    rol: discord.Role,
    premio: str,
    dato_curioso: str = None
):
    
    # 1. Confirmación privada (ephemeral) para el moderador
    await interaction.response.send_message(
        "✅ La pregunta ha sido ejecutada con éxito.", 
        ephemeral=True
    )

    # 2. Mensaje público con el embed de la pregunta y mención al rol
    embed = discord.Embed(
        title="📢 ¡Nueva Pregunta!",
        description=f"**Pregunta:** {pregunta}",
        color=discord.Color.blue()
    )
    embed.add_field(name="⏳ Tiempo", value=f"{tiempo_segundos} segundos", inline=True)
    embed.add_field(name="🎁 Premio", value=premio, inline=True)
    
    await interaction.channel.send(
        content=f"¡Atención {rol.mention}! Tienen un reto.", 
        embed=embed
    )

    # 3. Lógica de validación ultra flexible (sin tildes, sin mayúsculas)
    def check(message):
        if message.channel != interaction.channel or message.author.bot:
            return False
            
        # Limpiamos el texto del usuario y la respuesta oficial (minúsculas y sin tildes)
        texto_usuario = quitar_tildes(message.content.lower().strip())
        respuesta_correcta = quitar_tildes(respuesta.lower().strip())

        # A. Coincidencia directa (ej: "higado" == "higado")
        if texto_usuario == respuesta_correcta:
            return True

        # B. Si la respuesta oficial es larga y escriben la parte principal
        if texto_usuario in respuesta_correcta or respuesta_correcta.startswith(texto_usuario):
            if len(texto_usuario) > 3:
                return True

        # C. Tolerancia a errores de tipeo cercanos
        coincidencias = difflib.get_close_matches(texto_usuario, [respuesta_correcta], n=1, cutoff=0.70)
        if coincidencias:
            return True

        return False

    try:
        # Espera a que alguien responda correctamente dentro del tiempo límite
        msg = await bot.wait_for('message', check=check, timeout=float(tiempo_segundos))
        
        # 4. Mensaje normal cuando SÍ hay un ganador
        await interaction.channel.send(f"✅ ¡Correcto! {msg.author.mention} ha acertado y se lleva: **{premio}**")
        
        if dato_curioso:
            embed_curioso = discord.Embed(
                title="Dato curioso",
                description=dato_curioso,
                color=discord.Color.green()
            )
            await interaction.channel.send(embed=embed_curioso)
        
    except asyncio.TimeoutError:
        # 5. Embed cuando SE ACABA EL TIEMPO y nadie acertó
        embed_tiempo = discord.Embed(
            title="⏳ ¡Tiempo Agotado!",
            description=f"Nadie respondió correctamente. La respuesta era: `{respuesta}`",
            color=discord.Color.red()
        )
        
        if dato_curioso:
            embed_tiempo.add_field(name="Dato curioso", value=dato_curioso, inline=False)
        
        await interaction.channel.send(embed=embed_tiempo)
    
@bot.tree.command(name="msj_rapido", description="Envía un mensaje con el bot de forma oculta o responde a un mensaje.")
@app_commands.describe(
    texto="Lo que quieres escribir con el bot",
    id_mensaje="[Opcional] ID del mensaje al que quieres responder"
)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def msj_rapido(
    interaction: discord.Interaction, 
    texto: str, 
    id_mensaje: str = None
):
    try:
        # Si el usuario proporcionó un ID, intenta hacer un reply en el canal actual
        if id_mensaje:
            try:
                mensaje_objetivo = await interaction.channel.fetch_message(int(id_mensaje))
                await mensaje_objetivo.reply(texto)
            except discord.NotFound:
                await interaction.response.send_message("❌ No se encontró ningún mensaje con ese ID en este canal.", ephemeral=True)
                return
        else:
            # Si no puso ID, envía un mensaje normal al canal actual
            await interaction.channel.send(texto)

        # Confirmación privada para que nadie sepa que usaste el comando
        await interaction.response.send_message(
            "✅ Mensaje enviado con éxito.", 
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ No tengo permisos suficientes en este canal.", 
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Ocurrió un error: {e}", 
            ephemeral=True
        )
        

# Comando MENSAJEDM
@bot.tree.command(name="msjdm", description="Envía un mensaje directo a un usuario de forma anónima.")
@app_commands.describe(
    usuario="El usuario al que deseas enviarle el mensaje.",
    mensaje="El contenido del mensaje que se enviará por MD."
)
@app_commands.checks.has_permissions(administrator=True)
async def msjdm(interaction: discord.Interaction, usuario: discord.Member, mensaje: str):
    if usuario.bot:
        await interaction.response.send_message("No puedes enviar mensajes a otros bots.", ephemeral=True)
        return

    try:
        await usuario.send(mensaje)
        await interaction.response.send_message(f"Mensaje enviado exitosamente a {usuario.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"No se pudo enviar el mensaje a {usuario.mention}. Tiene los MDs cerrados.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Ocurrió un error: {e}", ephemeral=True)

@msjdm.error
async def msjdm_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.checks.MissingPermissions):
        await interaction.response.send_message("No tienes permisos de Administrador para usar este comando.", ephemeral=True)

@bot.tree.command(name="staff_activo", description="Muestra los miembros del staff que se encuentran activos actualmente")
async def staff_activo(interaction: discord.Interaction):
    # Buscamos el rol de staff usando su ID exacto
    rol_staff = interaction.guild.get_role(1501691450574770197)
    
    miembros_activos = []

    # Verificamos que el rol exista en el servidor
    if rol_staff:
        # Recorremos a los miembros que tienen ese rol asignado
        for member in rol_staff.members:
            if member.bot:
                continue
            
            # Comprobamos si su estado es diferente de offline (online, idle, dnd)
            if member.status != discord.Status.offline:
                miembros_activos.append(member.mention)

    # Creamos el embed con el título solicitado
    embed = discord.Embed(
        title="Usuarios activos",
        color=discord.Color.green()
    )

    if miembros_activos:
        # Añade las menciones clickeables separadas por saltos de línea
        embed.description = "\n".join(miembros_activos)
    else:
        embed.description = "No hay ningún miembro del staff activo en este momento."

    # Enviamos la respuesta de forma pública
    await interaction.response.send_message(embed=embed)

# ==========================================
# 1. Comando /editmsj
# ==========================================
@bot.tree.command(name="editmsj", description="Edita un mensaje enviado previamente por el bot.")
@app_commands.describe(
    link_o_id="El ID o el enlace del mensaje del bot que quieres editar",
    nuevo_texto="El nuevo contenido que tendrá el mensaje"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def editmsj(interaction: discord.Interaction, link_o_id: str, nuevo_texto: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        if "discord.com/channels/" in link_o_id:
            message_id = int(link_o_id.split("/")[-1])
        else:
            message_id = int(link_o_id)
            
        mensaje = await interaction.channel.fetch_message(message_id)
        
        if mensaje.author.id != bot.user.id:
            await interaction.followup.send("❌ Solo puedo editar mensajes que yo haya enviado.", ephemeral=True)
            return
            
        await mensaje.edit(content=nuevo_texto)
        await interaction.followup.send("✅ ¡Mensaje editado con éxito!", ephemeral=True)
        
    except discord.NotFound:
        await interaction.followup.send("❌ No se encontró el mensaje en este canal.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ No tengo permisos para editar ese mensaje.", ephemeral=True)
    except ValueError:
        await interaction.followup.send("❌ El ID o enlace proporcionado no es válido.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ocurrió un error: {e}", ephemeral=True)


# ==========================================
# 2. Comando /reaction
# ==========================================
@bot.tree.command(name="reaction", description="Reacciona a cualquier mensaje con un emoji.")
@app_commands.describe(
    link_o_id="El ID o el enlace del mensaje al que quieres reaccionar",
    emoji="El emoji que usará el bot (nativo o personalizado)"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def reaction(interaction: discord.Interaction, link_o_id: str, emoji: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        if "discord.com/channels/" in link_o_id:
            message_id = int(link_o_id.split("/")[-1])
        else:
            message_id = int(link_o_id)
            
        mensaje = await interaction.channel.fetch_message(message_id)
        await mensaje.add_reaction(emoji)
        await interaction.followup.send("✅ ¡Reacción agregada con éxito!", ephemeral=True)
        
    except discord.NotFound:
        await interaction.followup.send("❌ No se encontró el mensaje en este canal.", ephemeral=True)
    except discord.HTTPException:
        await interaction.followup.send("❌ No pude reaccionar con ese emoji. Verifica que sea válido o que tenga acceso a él.", ephemeral=True)
    except ValueError:
        await interaction.followup.send("❌ El ID o enlace proporcionado no es válido.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ocurrió un error: {e}", ephemeral=True)


# ==========================================
# 3. Comando /sticker (Con selector visual privado)
# ==========================================
class StickerSelectView(discord.ui.View):
    def __init__(self, stickers):
        super().__init__(timeout=60)
        options = []
        for s in stickers[:25]:
            options.append(
                discord.SelectOption(
                    label=s.name, 
                    description=f"Formato: {s.format.name}", 
                    emoji="🖼️", 
                    value=str(s.id)
                )
            )
        self.add_item(StickerSelect(options, stickers))

class StickerSelect(discord.ui.Select):
    def __init__(self, options, stickers):
        super().__init__(placeholder="Elige un sticker para enviar...", min_values=1, max_values=1, options=options)
        self.stickers = stickers

    async def callback(self, interaction: discord.Interaction):
        selected_id = int(self.values[0])
        sticker_a_enviar = discord.utils.get(self.stickers, id=selected_id)
        
        if sticker_a_enviar:
            # Respondemos de forma efímera para ocultar el menú desplegable y que no quede rastro
            await interaction.response.send_message("✅ Sticker enviado con éxito.", ephemeral=True)
            # El bot envía el sticker al canal de forma pública (como si fuera una acción del bot)
            await interaction.channel.send(stickers=[sticker_a_enviar])
        else:
            await interaction.response.send_message("❌ El sticker ya no está disponible.", ephemeral=True)

@bot.tree.command(name="sticker", description="Muestra un menú visual privado para seleccionar y enviar un sticker.")
@app_commands.checks.has_permissions(manage_messages=True)
async def sticker(interaction: discord.Interaction):
    if not interaction.guild.stickers:
        await interaction.response.send_message("❌ Este servidor no tiene ningún sticker guardado.", ephemeral=True)
        return
        
    view = StickerSelectView(interaction.guild.stickers)
    # ephemeral=True oculta el menú y el comando ejecutado para que los demás miembros no vean quién lo usó
    await interaction.response.send_message(
        "📂 **Selecciona un sticker del menú desplegable:**", 
        view=view, 
        ephemeral=True
    )


# ==========================================
# 4. Comando /image
# ==========================================
@bot.tree.command(name="image", description="Envía una imagen de forma oculta/anónima mediante el bot.")
@app_commands.describe(
    archivo="Sube una imagen desde tu dispositivo o galería",
    enlace="O pega el enlace URL directo de una imagen"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def image(interaction: discord.Interaction, archivo: discord.Attachment = None, enlace: str = None):
    if not archivo and not enlace:
        await interaction.response.send_message("❌ Debes adjuntar un archivo de imagen o proporcionar un enlace.", ephemeral=True)
        return
        
    # Usamos ephemeral=True para que Discord oculte el comando (/image con su archivo/enlace) del chat público
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    try:
        if archivo:
            if not archivo.content_type or not archivo.content_type.startswith("image/"):
                await interaction.followup.send("❌ El archivo adjunto debe ser una imagen válida.", ephemeral=True)
                return
            
            imagen_enviar = await archivo.to_file()
            # Enviamos la imagen directamente al canal de forma limpia y pública (sin rastro de quién ejecutó el comando)
            await interaction.channel.send(file=imagen_enviar)
            
        elif enlace:
            # Enviamos el enlace de forma limpia y pública en el canal
            await interaction.channel.send(enlace)
            
        # Confirmación privada al moderador de que se envió correctamente
        await interaction.followup.send("✅ ¡Imagen enviada de forma anónima correctamente!", ephemeral=True)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Ocurrió un error al enviar la imagen: {e}", ephemeral=True)


# ==========================================
# Manejador de errores de permisos para los 4 comandos
# ==========================================
@editmsj.error
@reaction.error
@sticker.error
@image.error
async def permisos_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ No tienes permisos de **Manejar mensajes** (`Manage Messages`) para usar este comando.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No tienes permisos de **Manejar mensajes** (`Manage Messages`) para usar este comando.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Ocurrió un error: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Ocurrió un error: {error}", ephemeral=True)

@bot.tree.command(name="video", description="Envía un video seleccionado desde tus archivos.")
@app_commands.describe(
    archivo="Selecciona el archivo de video que deseas enviar",
    mensaje="Un texto opcional para acompañar tu video"
)
@app_commands.checks.has_permissions(manage_messages=True)
async def video(interaction: discord.Interaction, archivo: discord.Attachment, mensaje: str = None):
    extensiones_validas = ('.mp4', '.mov', '.avi', '.mkv', '.webm')
    
    if not archivo.filename.lower().endswith(extensiones_validas):
        await interaction.response.send_message(
            "❌ **Error:** Por favor, sube un archivo de video válido (Formatos permitidos: MP4, MOV, AVI, MKV, WEBM).", 
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        f = await archivo.to_file()
        # Envía el video y el texto de forma pública al canal
        await interaction.channel.send(content=mensaje, file=f)
        
        # Envía una confirmación privada (ephemeral) solo para ti de que se publicó con éxito
        await interaction.followup.send("✅ Vídeo publicado con éxito", ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Ocurrió un error al intentar enviar el video: `{e}`", 
            ephemeral=True
        )



# ==================== SERVIDOR FLASK ====================
def quitar_tildes(texto): return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    
@app.route('/')
def health_check():
    return {'status': 'Bot is running'}, 200

@app.route('/health')
def health():
    return {'status': 'OK'}, 200

def run_flask():
    """Ejecuta el servidor Flask en un thread separado"""
    app.run(host='0.0.0.0', port=8000, debug=False)

# ==================== INICIO ====================

if __name__ == '__main__':
    # Iniciar Flask en un thread separado
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Ejecutar el bot de Discord
    bot.run(DISCORD_TOKEN)
