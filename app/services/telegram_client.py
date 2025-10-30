"""
Telegram Client Service using Telethon for channel discovery and interaction
"""

from telethon import TelegramClient
from telethon.sessions import StringSession, SQLiteSession
from telethon.tl.types import Channel, Chat
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from typing import List, Dict, Optional, Tuple
import asyncio
import os
import tempfile
import base64


class TelegramClientService:
    """
    Service for interacting with Telegram API using Telethon
    Supports interactive OTP login and session file conversion
    """

    @staticmethod
    async def send_otp(
        api_id: int, api_hash: str, phone_number: str
    ) -> Tuple[str, str]:
        """
        Send OTP to phone number and return temporary session string + phone_code_hash

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            phone_number: Phone number with country code (e.g., +1234567890)

        Returns:
            Tuple of (session_string, phone_code_hash)
        """
        # Create a new session
        client = TelegramClient(StringSession(), api_id, api_hash)

        try:
            await client.connect()

            # Send code request
            sent_code = await client.send_code_request(phone_number)

            # Save the temporary session string
            session_string = client.session.save()

            # Get phone code hash for verification
            phone_code_hash = sent_code.phone_code_hash

            # Don't disconnect yet - we need the session active
            await client.disconnect()

            return session_string, phone_code_hash

        except Exception as e:
            await client.disconnect()
            raise Exception(f"Failed to send OTP: {str(e)}")

    @staticmethod
    async def verify_otp(
        api_id: int,
        api_hash: str,
        phone_number: str,
        code: str,
        phone_code_hash: str,
        session_string: str,
        password: Optional[str] = None,
    ) -> str:
        """
        Verify OTP code and complete login, returning final session string

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            phone_number: Phone number
            code: OTP code from user
            phone_code_hash: Hash from send_otp
            session_string: Temporary session string from send_otp
            password: 2FA password if required

        Returns:
            Final authenticated session string
        """
        # Restore the session
        client = TelegramClient(StringSession(session_string), api_id, api_hash)

        try:
            await client.connect()

            try:
                # Sign in with the code
                await client.sign_in(
                    phone=phone_number, code=code, phone_code_hash=phone_code_hash
                )
            except SessionPasswordNeededError:
                # 2FA is enabled
                if not password:
                    await client.disconnect()
                    raise Exception("2FA is enabled. Password required.")

                # Sign in with password
                await client.sign_in(password=password)
            except PhoneCodeInvalidError:
                await client.disconnect()
                raise Exception("Invalid OTP code")

            # Verify authorization
            if not await client.is_user_authorized():
                await client.disconnect()
                raise Exception("Authorization failed")

            # Get the final session string
            final_session_string = client.session.save()

            await client.disconnect()

            return final_session_string

        except Exception as e:
            await client.disconnect()
            raise Exception(f"Failed to verify OTP: {str(e)}")

    @staticmethod
    async def convert_session_file_to_string(
        session_file_content: bytes, api_id: int, api_hash: str
    ) -> Tuple[str, str]:
        """
        Convert a .session file to StringSession and extract phone number

        Args:
            session_file_content: Binary content of .session file
            api_id: Telegram API ID
            api_hash: Telegram API Hash

        Returns:
            Tuple of (session_string, phone_number)
        """
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix=".session", delete=False) as temp_file:
            temp_file.write(session_file_content)
            temp_path = temp_file.name

        try:
            # Remove .session extension for TelegramClient
            session_name = temp_path.replace(".session", "")

            # Create client with the file session
            client = TelegramClient(session_name, api_id, api_hash)

            await client.connect()

            # Verify the session is authorized
            if not await client.is_user_authorized():
                await client.disconnect()
                os.remove(temp_path)
                raise Exception("Session file is not authorized or expired")

            # Get user info to extract phone number
            me = await client.get_me()
            phone_number = f"+{me.phone}" if me.phone else None

            if not phone_number:
                await client.disconnect()
                os.remove(temp_path)
                raise Exception("Could not extract phone number from session")

            # Convert to string session
            string_session = StringSession.save(client.session)

            await client.disconnect()

            # Clean up temp file
            os.remove(temp_path)
            if os.path.exists(session_name):
                os.remove(session_name)

            return string_session, phone_number

        except Exception as e:
            # Clean up on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            session_name = temp_path.replace(".session", "")
            if os.path.exists(session_name):
                os.remove(session_name)

            raise Exception(f"Failed to convert session file: {str(e)}")

    @staticmethod
    async def get_user_channels(
        api_id: int, api_hash: str, session_string: str
    ) -> List[Dict]:
        """
        Fetch all channels and groups accessible by the user session

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_string: Telethon StringSession data

        Returns:
            List of channel information dictionaries
        """
        client = TelegramClient(StringSession(session_string), api_id, api_hash)

        try:
            await client.connect()

            if not await client.is_user_authorized():
                raise Exception("Session is not authorized")

            # Get all dialogs (chats, channels, groups)
            dialogs = await client.get_dialogs()

            channels = []
            for dialog in dialogs:
                entity = dialog.entity

                # Filter only channels and supergroups
                if isinstance(entity, Channel):
                    channel_info = {
                        "id": entity.id,
                        "username": (
                            entity.username if hasattr(entity, "username") else None
                        ),
                        "title": entity.title,
                        "participants_count": (
                            entity.participants_count
                            if hasattr(entity, "participants_count")
                            else None
                        ),
                        "is_broadcast": (
                            entity.broadcast if hasattr(entity, "broadcast") else False
                        ),
                        "is_megagroup": (
                            entity.megagroup if hasattr(entity, "megagroup") else False
                        ),
                        "access_hash": (
                            entity.access_hash
                            if hasattr(entity, "access_hash")
                            else None
                        ),
                        "is_private": (
                            not bool(entity.username)
                            if hasattr(entity, "username")
                            else True
                        ),
                        "description": (
                            entity.about if hasattr(entity, "about") else None
                        ),
                    }
                    channels.append(channel_info)

            return channels

        finally:
            await client.disconnect()

    @staticmethod
    async def verify_public_channel(
        api_id: int, api_hash: str, channel_identifier: str, session_string: str
    ) -> Dict:
        """
        Verify and get information about a public channel

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            channel_identifier: Channel username (@channel) or ID
            session_string: Telethon StringSession data

        Returns:
            Channel information dictionary
        """
        client = TelegramClient(StringSession(session_string), api_id, api_hash)

        try:
            await client.connect()

            # Get channel entity
            entity = await client.get_entity(channel_identifier)

            if not isinstance(entity, Channel):
                raise Exception("Identifier does not point to a channel")

            channel_info = {
                "id": entity.id,
                "username": entity.username if hasattr(entity, "username") else None,
                "title": entity.title,
                "participants_count": (
                    entity.participants_count
                    if hasattr(entity, "participants_count")
                    else None
                ),
                "is_broadcast": (
                    entity.broadcast if hasattr(entity, "broadcast") else False
                ),
                "is_megagroup": (
                    entity.megagroup if hasattr(entity, "megagroup") else False
                ),
                "access_hash": (
                    entity.access_hash if hasattr(entity, "access_hash") else None
                ),
                "is_private": False,
                "description": entity.about if hasattr(entity, "about") else None,
            }

            return channel_info

        finally:
            await client.disconnect()

    @staticmethod
    async def test_session(api_id: int, api_hash: str, session_string: str) -> bool:
        """
        Test if a session is valid and authorized

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_string: Telethon StringSession data

        Returns:
            True if session is valid and authorized, False otherwise
        """
        client = TelegramClient(StringSession(session_string), api_id, api_hash)

        try:
            await client.connect()
            is_authorized = await client.is_user_authorized()
            return is_authorized
        except Exception as e:
            print(f"Session test failed: {e}")
            return False
        finally:
            await client.disconnect()
