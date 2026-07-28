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
from deep_translator import GoogleTranslator
from discord.ui import View, Select, Button
import re
from datetime import datetime, timedelta
from pymongo import MongoClient
from datetime import datetime, timezone




load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Cliente de Groq (lo mantienes con su nombre original)
client = Groq(api_key=os.environ.get("GROQ_API_KEY")) 

# Cliente de MongoDB
MONGO_URI = os.getenv('MONGO_URI')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["z6bot_database"] 

# Colecciones de MongoDB
respuestas_collection = db["respuestas_guilds"]
afk_collection = db["afk"]
warns_collection = db["warns"]
permisos_links_collection = db["permisos_links"]

# Inicializar bot de Discord
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="?", intents=intents)



# Inicializar Flask
app = Flask(__name__)

# Funciones para manejar respuestas automáticas en la nube con Supabase
# Funciones para manejar respuestas automáticas en la nube con Supabase

def remover_ultimo_warn(user_id: str, guild_id: str):
    """Elimina el warn más reciente de un usuario en MongoDB y devuelve el total restante"""
    try:
        warns_collection = db["warns"]
        # Buscamos el último warn registrado para este usuario en este servidor
        ultimo = warns_collection.find_one(
            {"user_id": str(user_id), "guild_id": str(guild_id)},
            sort=[("_id", -1)]
        )
        if ultimo:
            warns_collection.delete_one({"_id": ultimo["_id"]})
        
        # Devolvemos cuántos warns le quedan
        total_restante = warns_collection.count_documents({"user_id": str(user_id), "guild_id": str(guild_id)})
        return total_restante
    except Exception as e:
        print(f"Error al remover warn: {e}")
        return None
        
def registrar_warn_y_verificar(user_id: str, guild_id: str, razon: str):
    try:
        warns_collection.insert_one({
            "user_id": str(user_id),
            "guild_id": str(guild_id),
            "razon": razon,
            "fecha": datetime.now(timezone.utc)
        })
        return warns_collection.count_documents({"user_id": str(user_id), "guild_id": str(guild_id)})
    except Exception as e:
        print(f"Error al registrar warn: {e}")
        return 0

def otorgar_permiso_link(target_id: str, guild_id: str, tipo: str):
    try:
        permisos_links_collection.update_one(
            {"target_id": str(target_id), "guild_id": str(guild_id)},
            {"$set": {"tipo": tipo}},
            upsert=True
        )
    except Exception as e:
        print(f"Error guardando permiso de link: {e}")

def tiene_permiso_link(member: discord.Member):
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    guild_id = str(member.guild.id)
    user_id = str(member.id)
    if permisos_links_collection.find_one({"target_id": user_id, "guild_id": guild_id}):
        return True
    for rol in member.roles:
        if permisos_links_collection.find_one({"target_id": str(rol.id), "guild_id": guild_id}):
            return True
    return False
    
def cargar_respuestas_guild(guild_id: str):
    """Carga las respuestas de un servidor especifico desde MongoDB"""
    try:
        # Buscamos un documento que coincida con el guild_id
        resultado = respuestas_collection.find_one({"guild_id": str(guild_id)})
        
        if resultado and "datos" in resultado:
            return resultado["datos"]
        return {}
    except Exception as e:
        print(f"❌ Error al cargar de MongoDB: {e}")
        return {}

def guardar_respuestas_guild(guild_id: str, datos: dict):
    """Guarda o actualiza las respuestas de un servidor en MongoDB (Upsert)"""
    try:
        # Usamos update_one con upsert=True para insertar si no existe o actualizar si ya existe
        respuestas_collection.update_one(
            {"guild_id": str(guild_id)},
            {"$set": {"datos": datos}},
            upsert=True
        )
    except Exception as e:
        print(f"❌ Error al guardar en MongoDB: {e}")
        
        

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


# ==========================================
# EVENTO UNIFICADO on_message (Completo y Actualizado)
# ==========================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id) if message.guild else "dm"

    # --- A. FILTRO POTENTE DE LINKS Y ALERTA DE SEGURIDAD ---
    if "http://" in message.content.lower() or "https://" in message.content.lower() or "www." in message.content.lower() or "discord.gg/" in message.content.lower():
        if message.guild and not tiene_permiso_link(message.author):
            try:
                await message.delete()
                total_w = registrar_warn_y_verificar(str(message.author.id), guild_id, "Envío de link no autorizado")

                canal_alerta = message.guild.get_channel(1501692089170399343)
                if canal_alerta:
                    embed_alerta = discord.Embed(
                        title="🚨 ¡Alerta de Seguridad: Link Bloqueado!",
                        description="Se ha detectado y bloqueado un enlace no autorizado.",
                        color=discord.Color.red()
                    )
                    embed_alerta.add_field(name="👤 Usuario", value=f"{message.author.mention}", inline=True)
                    embed_alerta.add_field(name="📍 Canal", value=message.channel.mention, inline=True)
                    embed_alerta.add_field(name="🔗 Contenido", value=f"```{message.content}```", inline=False)
                    embed_alerta.add_field(name="⚠️ Sanción", value=f"Mensaje borrado. Warns: **{total_w}/5**", inline=False)
                    
                    await canal_alerta.send(embed=embed_alerta)
                
                aviso = await message.channel.send(f"⚠️ {message.author.mention}, no tienes permisos para enviar links aquí, bro.")
                await asyncio.sleep(5)
                await aviso.delete()
                return
            except Exception as e:
                print(f"Error en filtro de links: {e}")

    # --- B. QUITAR ESTADO AFK SI EL USUARIO ESCRIBE ---
    datos_afk = afk_collection.find_one({"user_id": user_id})
    if datos_afk and datos_afk.get("activo"):
        afk_collection.delete_one({"user_id": user_id})
        try:
            await message.channel.send(f"👋 ¡Bienvenido de vuelta, {message.author.mention}! Ya te retiré el estado AFK.")
        except discord.HTTPException:
            pass

    # --- C. ACTIVAR COMANDO AFK ---
    if message.content.lower().startswith("z6 afk"):
        partes = message.content.split(" ", 2)
        razon = partes[2] if len(partes) > 2 else "Sin razón especificada"

        afk_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "razon": razon, 
                "activo": True, 
                "tiempo_inicio": datetime.now(timezone.utc)
            }},
            upsert=True
        )

        embed_afk = discord.Embed(
            title="💤 ¡Modo AFK Activado!",
            description="Te has puesto ausente correctamente.",
            color=discord.Color.orange()
        )
        embed_afk.add_field(name="📌 Razón", value=razon, inline=False)
        embed_afk.set_footer(text="⚡ Se te quitará el estado en cuanto escribas un mensaje.")
        await message.reply(embed=embed_afk)
        return

    # --- D. DETECTAR MENCIONES A USUARIOS AFK ---
    if message.mentions:
        for user in message.mentions:
            user_afk_data = afk_collection.find_one({"user_id": str(user.id)})
            
            if user_afk_data and user_afk_data.get("activo"):
                razon = user_afk_data.get("razon", "Sin razón")
                tiempo_inicio = user_afk_data.get("tiempo_inicio")
                
                tiempo_texto = "hace un momento"
                if tiempo_inicio:
                    if tiempo_inicio.tzinfo is None:
                        tiempo_inicio = tiempo_inicio.replace(tzinfo=timezone.utc)
                    
                    diferencia = datetime.now(timezone.utc) - tiempo_inicio
                    segundos = int(diferencia.total_seconds())
                    horas, minutos = segundos // 3600, (segundos % 3600) // 60
                    
                    partes_t = []
                    if horas > 0: partes_t.append(f"{horas} hora{'s' if horas > 1 else ''}")
                    if minutos > 0 or horas == 0: partes_t.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
                    tiempo_texto = f"hace {' y '.join(partes_t)}"

                accion_extra = None
                for activity in user.activities:
                    if isinstance(activity, discord.Spotify):
                        accion_extra = f"🎵 Escuchando **{activity.title}** de {', '.join(activity.artists)} en Spotify"
                        break
                
                aviso_afk = f"💤 El usuario **{user.name}** está AFK **{tiempo_texto}**.\n📌 **Razón:** {razon}"
                if accion_extra: aviso_afk += f"\n{accion_extra}"
                
                try:
                    await message.channel.send(aviso_afk)
                except discord.HTTPException:
                    pass

    # --- E. SISTEMA SAVETEXTO (MongoDB con validación de roles) ---
    if message.guild:
        savetextos_collection = db["savetextos"]
        texto_guardado = savetextos_collection.find_one({
            "guild_id": guild_id, 
            "activador": message.content.strip().lower()
        })
        if texto_guardado:
            try:
                roles_permitidos = texto_guardado.get("roles", "todos")
                
                tiene_acceso = False
                if roles_permitidos == "todos":
                    tiene_acceso = True
                elif message.author.guild_permissions.administrator:
                    tiene_acceso = True
                elif isinstance(roles_permitidos, list):
                    tiene_acceso = any(rol.id in roles_permitidos for rol in message.author.roles)

                if tiene_acceso:
                    await message.channel.send(texto_guardado["contenido"])
                    return
            except Exception as e:
                print(f"Error al enviar savetexto: {e}")

    # --- F. COMANDO INTELIGENTE (IA CON PERSONALIDAD CHILL, ACCIONES TOTALES Y JERARQUÍA) ---
    if bot.user in message.mentions:
        pregunta = message.content
        for mention in message.mentions:
            pregunta = pregunta.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "").strip()

        contexto_historial = []
        mensaje_actual = message

        if message.reference and message.reference.message_id:
            try:
                msg_reply = await message.channel.fetch_message(message.reference.message_id)
                if msg_reply:
                    contexto_historial.append({
                        "role": "user",
                        "content": f"[El usuario hizo reply al mensaje de {msg_reply.author.display_name}]: {msg_reply.content or '[Mensaje sin texto]'}"
                    })
            except Exception as e:
                print(f"Error en reply directo: {e}")

        for _ in range(5):
            if mensaje_actual.reference and mensaje_actual.reference.message_id:
                try:
                    mensaje_ref = await message.channel.fetch_message(mensaje_actual.reference.message_id)
                    if mensaje_ref:
                        rol_ref = "assistant" if mensaje_ref.author == bot.user else "user"
                        contexto_historial.insert(0, {
                            "role": rol_ref, 
                            "content": f"[{mensaje_ref.author.display_name}]: {mensaje_ref.content or '[Vacío]'}"
                        })
                        mensaje_actual = mensaje_ref
                    else:
                        break
                except Exception:
                    break
            else:
                break

        async with message.channel.typing():
            try:
                system_prompt = (
                    "Eres un tío súper chill, relajado de cojones, con buen rollo y hablas de forma natural (usando términos como 'bro', 'tío', 'xd'). "
                    "EXCEPCIÓN 1 (MODERACIÓN SERIA): En cuanto te ordenen aplicar una sanción (warn, mute, kick, ban, unwarn, unban), ponte 100% serio y formal. Añade al final: [ACCION: tipo | usuario_o_id | razon]. "
                    "EXCEPCIÓN 2 (ADMINISTRACIÓN TOTAL Y AVANZADA): "
                    "- Si piden crear un rol, añade: [CREAR_ROL: nombre | color]. "
                    "- Si piden crear un canal, añade: [CREAR_CANAL: nombre | texto/voz]. "
                    "- Si piden dar un rol, añade: [DAR_ROL]. "
                    "- Si piden quitar un rol, añade: [QUITAR_ROL]. "
                    "- Si piden subir o mover un rol de posición, añade: [SUBIR_ROL: @rol | posicion_numerica]. "
                    "- Si piden cambiar permisos a un rol, añade: [PERMISOS_ROL: @rol | admin/moderador/basico]. "
                    "EXCEPCIÓN 3 (PERMISO DE LINKS): Si piden dar permisos de links, añade: [PERMISO_LINK: id | tipo]. "
                    "REGLAS: Responde solo en español. Para usar emojis personalizados (como Borja o Embobao), escríbelos usando su estructura exacta con ID (ej: <:borja:ID>). Máximo 75 palabras."
                )

                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(contexto_historial)
                messages.append({"role": "user", "content": pregunta or "¿Qué onda?"})

                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    max_tokens=120,
                    temperature=0.7,
                )

                reply_text = completion.choices[0].message.content or "xd."

                async def enviar_log_moderacion(guild, titulo, descripcion_accion, usuario_afectado_str, moderador):
                    try:
                        canal_logs = guild.get_channel(1501692089170399343)
                        if canal_logs:
                            embed_log = discord.Embed(
                                title=f"🛡️ {titulo}",
                                description=descripcion_accion,
                                color=discord.Color.dark_red() if "Ban" in titulo or "Mut" in titulo else discord.Color.gold()
                            )
                            embed_log.add_field(name="👤 Usuario Afectado", value=usuario_afectado_str, inline=True)
                            embed_log.add_field(name="👮 Moderador / Sistema", value=f"{moderador.mention} (`{moderador.id}`)", inline=True)
                            embed_log.set_footer(text="⚡ Registro de seguridad automatizado z6")

                            await canal_logs.send(embed=embed_log)
                    except Exception as e:
                        print(f"Error enviando log al canal: {e}")

                # 1. EJECUCIÓN DE MODERACIÓN
                if "[ACCION:" in reply_text and message.guild:
                    if message.author.guild_permissions.ban_members or message.author.guild_permissions.administrator:
                        try:
                            partes = reply_text.split("[ACCION:")[1].split("]")[0].split("|")
                            tipo = partes[0].strip().lower()
                            reply_text = reply_text.split("[ACCION:")[0].strip()
                            razon = partes[2].strip() if len(partes) > 2 else "Acción vía IA"

                            if tipo == "unban":
                                id_a_desbanear = partes[1].strip().replace("<@", "").replace(">", "").replace("!", "").strip()
                                usuario_obj = await bot.fetch_user(int(id_a_desbanear))
                                await message.guild.unban(usuario_obj, reason=razon)
                                await message.channel.send(f"🔓 He desbaneado correctamente a **{usuario_obj.name}**. Razón: {razon}")
                                await enviar_log_moderacion(message.guild, "Usuario Desbaneado", f"**Razón:** {razon}", f"**{usuario_obj.name}** (`{usuario_obj.id}`)", message.author)
                            
                            elif message.mentions:
                                obj = message.mentions[0]

                                if tipo == "warn":
                                    tw = registrar_warn_y_verificar(str(obj.id), guild_id, razon)
                                    msg_w = f"⚠️ Warn emitido a {obj.mention} (Total: **{tw}/5**). Razón: {razon}"
                                    
                                    if tw >= 5:
                                        await message.guild.ban(obj, reason="5 warns automáticos")
                                        msg_w += f"\n🔨 {obj.mention} alcanzó los 5 warns y fue **baneado automáticamente**."
                                        await enviar_log_moderacion(message.guild, "Baneo Automático (5 Warns)", f"**Razón:** Límite de warns alcanzado", f"{obj.mention} (`{obj.id}`)", bot.user)
                                    elif tw >= 3:
                                        await obj.timeout(timedelta(hours=2), reason="3 warns automáticos")
                                        msg_w += f"\n🔇 {obj.mention} alcanzó los 3 warns y recibió un **mute automático de 2 horas**."
                                        await enviar_log_moderacion(message.guild, "Mute Automático (3 Warns)", f"**Razón:** Límite de warns alcanzado", f"{obj.mention} (`{obj.id}`)", bot.user)
                                    else:
                                        await enviar_log_moderacion(message.guild, "Warn Registrado", f"**Razón:** {razon}\n**Total Warns:** {tw}/5", f"{obj.mention} (`{obj.id}`)", message.author)

                                    await message.channel.send(msg_w)
                                
                                elif tipo == "unwarn":
                                    restantes = remover_ultimo_warn(str(obj.id), guild_id)
                                    await message.channel.send(f"✨ Se le ha retirado el último warn a {obj.mention}. Warns actuales: **{restantes}/5**")
                                    await enviar_log_moderacion(message.guild, "Warn Removido (Unwarn)", f"**Warns restantes:** {restantes}/5", f"{obj.mention} (`{obj.id}`)", message.author)
                                
                                elif tipo == "ban":
                                    await message.guild.ban(obj, reason=razon)
                                    await message.channel.send(f"🔨 Baneado {obj.mention}. Razón: {razon}")
                                    await enviar_log_moderacion(message.guild, "Usuario Baneado", f"**Razón:** {razon}", f"{obj.mention} (`{obj.id}`)", message.author)
                                
                                elif tipo == "kick":
                                    await message.guild.kick(obj, reason=razon)
                                    await message.channel.send(f"👢 Expulsado {obj.mention}. Razón: {razon}")
                                    await enviar_log_moderacion(message.guild, "Usuario Expulsado (Kick)", f"**Razón:** {razon}", f"{obj.mention} (`{obj.id}`)", message.author)
                                
                                elif tipo == "mute":
                                    await obj.timeout(timedelta(minutes=15), reason=razon)
                                    await message.channel.send(f"🔇 Silenciado {obj.mention} por 15 minutos. Razón: {razon}")
                                    await enviar_log_moderacion(message.guild, "Usuario Silenciado (Mute)", f"**Razón:** {razon}", f"{obj.mention} (`{obj.id}`)", message.author)
                        except Exception as e:
                            print(f"Error mod/revertir: {e}")

                # 2. CREAR ROL
                if "[CREAR_ROL:" in reply_text and message.guild:
                    if message.author.guild_permissions.manage_roles or message.author.guild_permissions.administrator:
                        try:
                            partes_r = reply_text.split("[CREAR_ROL:")[1].split("]")[0].split("|")
                            nombre_r, color_r = partes_r[0].strip(), partes_r[1].strip().lower() if len(partes_r) > 1 else "default"
                            reply_text = reply_text.split("[CREAR_ROL:")[0].strip()
                            
                            colores = {"rojo": discord.Color.red(), "azul": discord.Color.blue(), "verde": discord.Color.green(), "amarillo": discord.Color.gold(), "morado": discord.Color.purple()}
                            nuevo_r = await message.guild.create_role(name=nombre_r, color=colores.get(color_r, discord.Color.default()))
                            await message.channel.send(f"🎨 ¡Rol **{nuevo_r.name}** creado con éxito, bro!")
                        except Exception as e:
                            print(f"Error rol: {e}")

                # 3. CREAR CANAL
                if "[CREAR_CANAL:" in reply_text and message.guild:
                    if message.author.guild_permissions.manage_channels or message.author.guild_permissions.administrator:
                        try:
                            partes_c = reply_text.split("[CREAR_CANAL:")[1].split("]")[0].split("|")
                            nombre_c = partes_c[0].strip()
                            tipo_c = partes_c[1].strip().lower() if len(partes_c) > 1 else "texto"
                            reply_text = reply_text.split("[CREAR_CANAL:")[0].strip()
                            
                            if "voz" in tipo_c:
                                nuevo_c = await message.guild.create_voice_channel(name=nombre_c)
                            else:
                                nuevo_c = await message.guild.create_text_channel(name=nombre_c)
                            await message.channel.send(f"📂 ¡Canal **{nuevo_c.name}** creado con éxito, bro!")
                        except Exception as e:
                            print(f"Error canal: {e}")

                # 4. DAR ROL A USUARIO
                if "[DAR_ROL]" in reply_text and message.guild and message.mentions:
                    if message.author.guild_permissions.manage_roles or message.author.guild_permissions.administrator:
                        try:
                            reply_text = reply_text.split("[DAR_ROL]")[0].strip()
                            usuario_obj = message.mentions[0]
                            rol_mencionado = message.role_mentions[0] if message.role_mentions else None
                            if rol_mencionado:
                                await usuario_obj.add_roles(rol_mencionado)
                                await message.channel.send(f"✨ Le asigné el rol **{rol_mencionado.name}** a {usuario_obj.mention}, bro.")
                        except Exception as e:
                            print(f"Error dar rol: {e}")

                # 5. QUITAR ROL A USUARIO
                if "[QUITAR_ROL]" in reply_text and message.guild and message.mentions:
                    if message.author.guild_permissions.manage_roles or message.author.guild_permissions.administrator:
                        try:
                            reply_text = reply_text.split("[QUITAR_ROL]")[0].strip()
                            usuario_obj = message.mentions[0]
                            rol_mencionado = message.role_mentions[0] if message.role_mentions else None
                            if rol_mencionado:
                                await usuario_obj.remove_roles(rol_mencionado)
                                await message.channel.send(f"✨ Le quité el rol **{rol_mencionado.name}** a {usuario_obj.mention}, bro.")
                         except Exception as e:
                             print(f"Error quitar rol: {e}")

class RepeatView(discord.ui.View):

  def __init__(self, duration_seconds: int, reason: str):
    super().__init__(timeout=None)
    self.duration_seconds = duration_seconds
    self.reason = reason

  @discord.ui.button(label="Repetir", emoji="🔃", style=discord.ButtonStyle.blurple)
  async def repeat_reminder(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    future_time = datetime.now() + timedelta(seconds=self.duration_seconds)
    timestamp = int(future_time.timestamp())

    reason_text = (
        f"**Razón:** {self.reason}"
        if self.reason
        else "**Razón:** No me dijiste una razón por la cuál debía recordarte"
    )

    embed = discord.Embed(
        title="⏰ ¡Recordatorio Repetido!",
        description=(
            f"📅 **Termina el:** <t:{timestamp}:F> (<t:{timestamp}:R>)\n\n"
            f"{reason_text}"
        ),
        color=discord.Color.blue(),
    )

    await interaction.response.send_message(
        content=f"{interaction.user.mention} (Recordatorio repetido)",
        embed=embed,
    )

    await asyncio.sleep(self.duration_seconds)

    final_embed = discord.Embed(
        title="🔔 ¡Tiempo cumplido (Repetido)!",
        description=reason_text,
        color=discord.Color.gold(),
    )
    # Aquí también se incluye la vista en el mensaje final repetido
    view = RepeatView(self.duration_seconds, self.reason)
    await interaction.followup.send(
        content=f"{interaction.user.mention}", embed=final_embed, view=view
    )


# Función para calcular los segundos según la unidad (s, m, h, d)
def parse_duration(time_str: str):
  match = re.match(r"^(\d+)([smhd])$", time_str.lower())
  if not match:
    return None
  amount, unit = match.groups()
  multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
  return int(amount) * multipliers[unit]


# Comando configurado directamente como 'rm' para usar con tu prefijo (ej. ;rm)
@bot.command(name="rm")
async def rm(ctx, time_str: str = None, *, reason=None):
  if not time_str:
    embed_error = discord.Embed(
        title="❌ Error de uso",
        description=(
            "Debes especificar un tiempo.\nEjemplo: `;rm 1h Estudiar matemáticas`"
        ),
        color=discord.Color.red(),
    )
    await ctx.send(embed=embed_error)
    return

  seconds = parse_duration(time_str)
  if not seconds:
    embed_error = discord.Embed(
        title="❌ Tiempo inválido",
        description=(
            "Usa un formato correcto (`s`, `m`, `h`, `d`).\nEjemplo: `30s`,"
            " `10m`, `1h`, `2d`"
        ),
        color=discord.Color.red(),
    )
    await ctx.send(embed=embed_error)
    return

  future_time = datetime.now() + timedelta(seconds=seconds)
  timestamp = int(future_time.timestamp())

  setup_embed = discord.Embed(
      title="⏰ ¡Recordatorio Establecido!",
      description=(
          f"📅 **Termina el:** <t:{timestamp}:F>\n⏳ **Faltan:**"
          f" <t:{timestamp}:R>"
      ),
      color=discord.Color.green(),
  )

  # Mensaje inicial SIN el botón de repetir
  await ctx.send(
      content=f"{ctx.author.mention} (Recordatorio guardado)", embed=setup_embed
  )

  await asyncio.sleep(seconds)

  if reason:
    reason_text = f"**Razón:** {reason}"
  else:
    reason_text = (
        "**Razón:** No me dijiste una razón por la cuál debía recordarte"
    )

  final_embed = discord.Embed(
      title="🔔 ¡Recordatorio Finalizado!",
      description=reason_text,
      color=discord.Color.orange(),
  )

  # Creamos la vista con el botón para adjuntarla al mensaje final
  view = RepeatView(seconds, reason)
  await ctx.send(
      content=f"{ctx.author.mention}", embed=final_embed, view=view
    )
    
             

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

# =========================================================
# CONFIGURACIÓN DEL ROSTER (Variables Globales)
# =========================================================
CANAL_ROSTER_ID = 1530204414873178382

ROSTER_ROLES = [
    1501691417146294282,  # Rango 1 (Más alto)
    1501691421340602518,  # Rango 2
    1501691439749267526,  # Rango 3 (Límite 2)
    1530154761720958976,  # Rango 4
    1530646309336387634,  # Rango 5 (Nuevo rol - Límite 3)
    1501691442433884261,  # Rango 6
    1501691445558644836,  # Rango 7
    1501691448368824320,  # Rango 8 (Más bajo)
]

ROSTER_LIMITES = {
    1501691417146294282: 1,
    1501691421340602518: 1,
    1501691439749267526: 2,
    1530154761720958976: 3,
    1530646309336387634: 3,
    1501691442433884261: 4,
    1501691445558644836: 6,
    1501691448368824320: 10,
}


# ==========================================
# 1. VISTA DE SELECCIÓN DE ROLES (MongoDB)
# ==========================================

class SeleccionRolesView(discord.ui.View):
    def __init__(self, activador: str, mensaje: str):
        super().__init__(timeout=180)
        self.activador = activador
        self.mensaje = mensaje

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Selecciona los roles permitidos...", min_values=1, max_values=25)
    async def select_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        roles_ids = [role.id for role in select.values]
        await self.guardar_datos_mongo(interaction, roles_ids)

    @discord.ui.button(label="Todos", style=discord.ButtonStyle.success, emoji="🌍")
    async def btn_todos(self, interaction: discord.Interaction, button: Button):
        await self.guardar_datos_mongo(interaction, "todos")

    async def guardar_datos_mongo(self, interaction: discord.Interaction, roles_permitidos):
        guild_id = str(interaction.guild_id)
        try:
            savetextos_collection = db["savetextos"]
            
            # Guardamos o actualizamos directamente en MongoDB
            savetextos_collection.update_one(
                {"guild_id": guild_id, "activador": self.activador.strip().lower()},
                {"$set": {
                    "contenido": self.mensaje,
                    "roles": roles_permitidos
                }},
                upsert=True
            )
            
            rol_msg = "Todos los miembros" if roles_permitidos == "todos" else f"{len(roles_permitidos)} rol(es) seleccionado(s)"
            
            await interaction.response.edit_message(
                content=f"✅ **¡Respuesta guardada exitosamente en MongoDB!**\n\n📌 **Activador:** `{self.activador}`\n👥 **Roles permitidos:** {rol_msg}",
                view=None
            )
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ Error al guardar en MongoDB: {e}", view=None)


# ==========================================
# 2. ACCIONES PARA GESTIONAR TEXTOS EXISTENTES (MongoDB)
# ==========================================

class AccionesTextoView(discord.ui.View):
    def __init__(self, activador: str, mensaje_actual: str):
        super().__init__(timeout=180)
        self.activador = activador
        self.mensaje_actual = mensaje_actual

    @discord.ui.button(label="Borrar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def borrar_btn(self, interaction: discord.Interaction, button: Button):
        guild_id = str(interaction.guild_id)
        savetextos_collection = db["savetextos"]

        resultado = savetextos_collection.delete_one({
            "guild_id": guild_id,
            "activador": self.activador.strip().lower()
        })

        if resultado.deleted_count > 0:
            await interaction.response.edit_message(
                content=f"🗑️ El texto con activador **`{self.activador}`** ha sido borrado exitosamente.",
                view=None
            )
            return

        await interaction.response.edit_message(content="❌ No se encontró el texto para borrar en la base de datos.", view=None)

    @discord.ui.button(label="Editar", style=discord.ButtonStyle.primary, emoji="✏️")
    async def editar_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ModalEditarTexto(self.activador, self.mensaje_actual))

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancelar_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="❌ Operación cancelada.", view=None)


class ModalEditarTexto(discord.ui.Modal, title="Editar Respuesta Automática"):
    def __init__(self, activador: str, mensaje_actual: str):
        super().__init__()
        self.activador = activador

        self.nuevo_mensaje = discord.ui.TextInput(
            label="Nuevo Mensaje",
            style=discord.TextStyle.paragraph,
            default=mensaje_actual,
            required=True
        )
        self.add_item(self.nuevo_mensaje)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        nuevo_texto = self.nuevo_mensaje.value

        try:
            savetextos_collection = db["savetextos"]
            resultado = savetextos_collection.update_one(
                {"guild_id": guild_id, "activador": self.activador.strip().lower()},
                {"$set": {"contenido": nuevo_texto}}
            )
            
            if resultado.matched_count > 0:
                await interaction.response.send_message(
                    content=f"✅ El texto para **`{self.activador}`** ha sido actualizado exitosamente.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message("❌ Error: No se encontró el activador en este servidor.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error al actualizar el texto: {e}", ephemeral=True)


class SeleccionTextoSelect(discord.ui.Select):
    def __init__(self, textos_cursor):
        options = []
        # Convertimos el cursor de MongoDB a lista para manejar los primeros 25
        self.textos_lista = list(textos_cursor)[:25]
        
        for doc in self.textos_lista:
            act = doc["activador"]
            options.append(discord.SelectOption(label=act, description=f"Ver respuesta para: {act}"))

        super().__init__(placeholder="Elige un texto para gestionar...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        activador_seleccionado = self.values[0]
        
        # Buscamos el documento específico en MongoDB
        savetextos_collection = db["savetextos"]
        doc = savetextos_collection.find_one({
            "guild_id": str(interaction.guild_id),
            "activador": activador_seleccionado
        })

        mensaje_guardado = doc.get("contenido", "Sin contenido") if doc else "Sin contenido"

        view = AccionesTextoView(activador_seleccionado, mensaje_guardado)
        await interaction.response.edit_message(
            content=f"🔑 **Activador:** `{activador_seleccionado}`\n\n💬 **Mensaje:**\n{mensaje_guardado}",
            view=view
        )


class VerTextoView(discord.ui.View):
    def __init__(self, textos_cursor):
        super().__init__(timeout=180)
        self.add_item(SeleccionTextoSelect(textos_cursor))


# ==========================================
# 3. COMANDOS SLASH /VERTEXTO Y /SAVETEXTO
# ==========================================

@bot.tree.command(name="vertexto", description="Muestra una lista con los textos guardados para gestionarlos")
@app_commands.checks.has_permissions(administrator=True)
async def vertexto(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)

    try:
        savetextos_collection = db["savetextos"]
        textos_cursor = list(savetextos_collection.find({"guild_id": guild_id}))

        if not textos_cursor:
            await interaction.followup.send("⚠️ No hay textos guardados en este servidor.", ephemeral=True)
            return

        view = VerTextoView(textos_cursor)
        await interaction.followup.send("Selecciona de la lista el texto que deseas ver o administrar:", view=view, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Ocurrió un error al leer los textos: {e}", ephemeral=True)


class ModalGuardarTexto(discord.ui.Modal, title="Guardar Nueva Respuesta"):
    activador = discord.ui.TextInput(
        label="Activador (palabra clave)",
        placeholder="Ej: hola o ¡ayuda",
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

        view = SeleccionRolesView(activador=act, mensaje=msg)

        await interaction.response.send_message(
            f"✅ El texto para **`{act}`** está casi listo.\n\n👇 Por favor, selecciona qué roles pueden usar este comando:",
            view=view,
            ephemeral=True
        )


@bot.tree.command(name="savetexto", description="Guarda un texto personalizado asociado a un activador")
@app_commands.checks.has_permissions(administrator=True)
async def savetexto(interaction: discord.Interaction):
    modal = ModalGuardarTexto()
    await interaction.response.send_modal(modal)


@savetexto.error
async def savetexto_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "❌ No tienes permisos de **Administrador** para usar este comando.",
            ephemeral=True
        )
        

# =========================================================
# COMANDO UPDATEROASTER
# =========================================================
@bot.command(name="updateroaster")
@commands.has_permissions(administrator=True)
async def updateroaster(ctx):
  try:
    await ctx.message.delete()
  except Exception:
    pass

  guild = ctx.guild
  canal = guild.get_channel(CANAL_ROSTER_ID)

  if not canal:
    await ctx.send(
        "❌ No se pudo encontrar el canal configurado con ese ID.", delete_after=5
    )
    return

  try:
    await canal.purge()
  except discord.Forbidden:
    await ctx.send(
        "❌ El bot no tiene permisos de 'Gestionar mensajes' en ese canal.",
        delete_after=5,
    )
    return
  except Exception as e:
    await ctx.send(f"❌ Ocurrió un error al limpiar el canal: {e}", delete_after=5)
    return

  try:
    await guild.chunk()
  except Exception:
    pass

  miembros_por_rol = {role_id: [] for role_id in ROSTER_ROLES}
  usuarios_ya_asignados = set()

  for role_id in ROSTER_ROLES:
    role = guild.get_role(role_id)
    if not role:
      continue

    limite = ROSTER_LIMITES[role_id]

    for member in role.members:
      if member.bot:
        continue
      if member.id not in usuarios_ya_asignados:
        if len(miembros_por_rol[role_id]) < limite:
          miembros_por_rol[role_id].append(member)
          usuarios_ya_asignados.add(member.id)

  def generar_bloque(role_id):
    limite = ROSTER_LIMITES[role_id]
    members = miembros_por_rol[role_id]
    actual = len(members)

    header = f"────── 『  <@&{role_id}>  ({actual}/{limite})  』 ──────"

    lines = []
    for i in range(limite):
      if i < actual:
        lines.append(f"•  » {members[i].mention}")
      else:
        lines.append("•  » ")

    return header + "\n\n" + "\n".join(lines) + "\n"

  try:
    parte_uno = f"""#   __➥ Roster de Z6 🛡️ __  

> • Organizado por la administración ✔️ 
> • 𝙕𝟲 ★ 𝙎𝙝𝙤𝙥
> • Creado por <@&1501691439749267526> 

{generar_bloque(1501691417146294282)}
{generar_bloque(1501691421340602518)}
{generar_bloque(1501691439749267526)}
{generar_bloque(1530154761720958976)}"""

    parte_dos = f"""{generar_bloque(1530646309336387634)}
{generar_bloque(1501691442433884261)}
{generar_bloque(1501691445558644836)}
{generar_bloque(1501691448368824320)}

*Si no estais en el roster ➡️ <@&1501691439749267526>*"""

    await canal.send(content=parte_uno)
    await canal.send(content=parte_dos)
    await ctx.send("✅ ¡Roster actualizado correctamente!", delete_after=4)

  except Exception as e:
    await ctx.send(
        f"⚠️ Error al enviar los mensajes del roster: ```{e}```",
        delete_after=10,
    )


@updateroaster.error
async def updateroaster_error(ctx, error):
  if isinstance(error, commands.MissingPermissions):
    await ctx.send(
        "❌ No tienes permisos de **Administrador** para ejecutar este comando.",
        delete_after=5,
    )
      
      
      

# ==========================================
# 2. COMANDO: /traducir (Con origen y destino personalizados)
# ==========================================
@bot.tree.command(
    name="traducir",
    description="Traduce un mensaje seleccionando el idioma de origen y el idioma de destino de forma limpia."
)
@app_commands.choices(
    idioma_de_origen=[
        app_commands.Choice(name="Español", value="es"),
        app_commands.Choice(name="Inglés", value="en"),
        app_commands.Choice(name="Francés", value="fr"),
        app_commands.Choice(name="Portugués", value="pt"),
        app_commands.Choice(name="Italiano", value="it"),
        app_commands.Choice(name="Alemán", value="de"),
        app_commands.Choice(name="Japonés", value="ja"),
        app_commands.Choice(name="Ruso", value="ru"),
    ],
    idioma_a_traducir=[
        app_commands.Choice(name="Español", value="es"),
        app_commands.Choice(name="Inglés", value="en"),
        app_commands.Choice(name="Francés", value="fr"),
        app_commands.Choice(name="Portugués", value="pt"),
        app_commands.Choice(name="Italiano", value="it"),
        app_commands.Choice(name="Alemán", value="de"),
        app_commands.Choice(name="Japonés", value="ja"),
        app_commands.Choice(name="Ruso", value="ru"),
    ]
)
@app_commands.describe(
    idioma_de_origen="Selecciona el idioma en el que está escrito tu mensaje original",
    idioma_a_traducir="Selecciona el idioma al que deseas traducir el mensaje",
    mensaje="El texto que deseas traducir"
)
@app_commands.checks.has_permissions(administrator=True)
async def traducir(interaction: discord.Interaction, idioma_de_origen: app_commands.Choice[str], idioma_a_traducir: app_commands.Choice[str], mensaje: str):
    await interaction.response.defer(ephemeral=True)
    
    try:
        traduccion = GoogleTranslator(source=idioma_de_origen.value, target=idioma_a_traducir.value).translate(mensaje)
        
        await interaction.channel.send(traduccion)
        
        await interaction.followup.send(
            f"✅ Traducido de **{idioma_de_origen.name}** a **{idioma_a_traducir.name}** y enviado correctamente.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(
            f"❌ Ocurrió un error al realizar la traducción.\n`Detalle: {e}`",
            ephemeral=True
        )

@traducir.error
async def traducir_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ No tienes permisos de administrador para usar este comando.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No tienes permisos de administrador para usar este comando.", ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Ocurrió un error: {error}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Ocurrió un error: {error}", ephemeral=True)
    
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
