"""
Guild-Specific Bot Profile Management

Handles per-server bot avatar, nickname, banner, and bio.
Uses Discord API endpoint: PATCH /guilds/{guild_id}/members/@me

This allows the bot to have different appearances in different servers.
"""

import aiohttp
import base64
from discord.ext import commands
from typing import Optional

import utils.func as func
from utils.http_client import create_http_session


async def bytes_to_data_uri(image_bytes: bytes) -> str:
    """
    Converte bytes de imagem para data URI base64.
    
    Args:
        image_bytes: Bytes da imagem
    
    Returns:
        str: Data URI no formato "data:image/png;base64,..."
    """
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    
    # Detecta tipo de imagem pelo magic number
    if image_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        mime = "image/jpeg"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        mime = "image/webp"
    elif image_bytes[:6] == b'GIF87a' or image_bytes[:6] == b'GIF89a':
        mime = "image/gif"
    else:
        # Fallback para PNG
        mime = "image/png"
    
    return f"data:{mime};base64,{encoded}"


async def set_guild_profile(
    bot: commands.Bot,
    guild_id: int,
    nick: Optional[str] = None,
    avatar_bytes: Optional[bytes] = None,
    banner_bytes: Optional[bytes] = None,
    bio: Optional[str] = None
) -> dict:
    """
    Define perfil do bot específico para um servidor.
    
    Este método usa o endpoint PATCH /guilds/{guild_id}/members/@me
    para definir avatar, nickname, banner e bio específicos do servidor.
    
    Args:
        bot: Instância do bot
        guild_id: ID do servidor
        nick: Nickname (apelido) do bot no servidor
        avatar_bytes: Bytes da imagem de avatar (PNG/JPEG/WEBP)
        banner_bytes: Bytes da imagem de banner (PNG/JPEG/WEBP)
        bio: Biografia do bot no servidor
    
    Returns:
        dict: Resposta da API do Discord
    
    Raises:
        Exception: Se a requisição falhar
    
    Note:
        - Avatar/Banner precisam ser enviados como data URI em base64
        - Nick pode ser string pura
        - Rate limit: Discord é restritivo com edições de perfil em sequência
    """
    payload = {}
    
    # Adiciona apenas os campos fornecidos
    if nick is not None:
        payload["nick"] = nick
    
    if avatar_bytes is not None:
        payload["avatar"] = await bytes_to_data_uri(avatar_bytes)
    
    if banner_bytes is not None:
        payload["banner"] = await bytes_to_data_uri(banner_bytes)
    
    if bio is not None:
        payload["bio"] = bio
    
    # Se nenhum campo foi fornecido, não faz nada
    if not payload:
        func.log.warning("set_guild_profile called with no parameters")
        return {}
    
    url = f"https://discord.com/api/v10/guilds/{guild_id}/members/@me"
    headers = {
        "Authorization": f"Bot {bot.http.token}",
        "Content-Type": "application/json"
    }
    
    func.log.info(f"Updating guild profile for guild {guild_id}: {list(payload.keys())}")
    
    async with create_http_session() as session:
        async with session.patch(url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                func.log.info(f"Successfully updated guild profile for guild {guild_id}")
                return await resp.json()
            else:
                text = await resp.text()
                error_msg = f"Failed to update guild profile (HTTP {resp.status}): {text}"
                func.log.error(error_msg)
                raise Exception(error_msg)


async def get_guild_profile(bot: commands.Bot, guild_id: int) -> Optional[dict]:
    """
    Obtém o perfil atual do bot no servidor.
    
    Args:
        bot: Instância do bot
        guild_id: ID do servidor
    
    Returns:
        dict: Dados do perfil ou None se falhar
    """
    url = f"https://discord.com/api/v10/guilds/{guild_id}/members/@me"
    headers = {
        "Authorization": f"Bot {bot.http.token}"
    }
    
    async with create_http_session() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                func.log.warning(f"Failed to get guild profile for guild {guild_id}: HTTP {resp.status}")
                return None


async def reset_guild_profile(bot: commands.Bot, guild_id: int) -> bool:
    """
    Reseta o perfil do bot no servidor para os valores globais.
    
    Args:
        bot: Instância do bot
        guild_id: ID do servidor
    
    Returns:
        bool: True se bem-sucedido
    """
    try:
        # Resetar enviando null para os campos
        payload = {
            "nick": None,
            "avatar": None
        }
        
        url = f"https://discord.com/api/v10/guilds/{guild_id}/members/@me"
        headers = {
            "Authorization": f"Bot {bot.http.token}",
            "Content-Type": "application/json"
        }
        
        async with create_http_session() as session:
            async with session.patch(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    func.log.info(f"Successfully reset guild profile for guild {guild_id}")
                    return True
                else:
                    func.log.error(f"Failed to reset guild profile: HTTP {resp.status}")
                    return False
    
    except Exception as e:
        func.log.error(f"Error resetting guild profile: {e}")
        return False
