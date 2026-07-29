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



# Cliente de MongoDB
MONGO_URI = os.getenv('MONGO_URI')
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["z6bot_database"] 

# Colecciones de MongoDB
respuestas_collection = db["respuestas_guilds"]
afk_collection = db["afk"]


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
# ==========================================
# EVENTO UNIFICADO on_message (Completo y Actualizado)
# ==========================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id) if message.guild else "dm"
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
                    print(f"No se pudo enviar el mensaje AFK: {e}")

 
    
           

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
