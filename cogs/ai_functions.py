import json
import os
import re
import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Tuple
from google import genai
from google.genai import types

DISCORD_MSG_LINK_RE = re.compile(r"https?://(?:canary\.|ptb\.)?discord\.com/channels/\d+/(?P<channel_id>\d+)/(?P<message_id>\d+)")
GEMINI_MODEL = "gemini-3.8-flash"
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
DISCORD_MENTION_RE = re.compile(r"<@!?\d+>|@&?\d+")
SNOWFLAKE_ID_RE = re.compile(r"\b\d{17,20}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s\-().]{7,}\d)(?!\w)")

class ReversibleAnonymizer:
    def __init__(self) -> None:
        self._value_to_token: dict[str, str] = {}
        self._token_to_value: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def _get_or_create_token(self, category: str, original_value: str):
        if original_value in self._value_to_token:
            return self._value_to_token[original_value]

        next_idx = self._counters.get(category, 0) + 1
        self._counters[category] = next_idx
        token = f"[[{category}_{next_idx}]]"
        self._value_to_token[original_value] = token
        self._token_to_value[token] = original_value
        return token

    def tokenize_author(self, author_name: str):
        return self._get_or_create_token("USER", author_name)

    def tokenize_text(self, text: str):
        def replace_match(category: str):
            def _sub(match: re.Match):
                return self._get_or_create_token(category, match.group(0))

            return _sub

        tokenized = DISCORD_MENTION_RE.sub(replace_match("MENTION"), text)
        tokenized = EMAIL_RE.sub(replace_match("EMAIL"), tokenized)
        tokenized = PHONE_RE.sub(replace_match("PHONE"), tokenized)
        tokenized = SNOWFLAKE_ID_RE.sub(replace_match("ID"), tokenized)
        return tokenized

    def restore(self, text: str):
        restored = text
        for token, original_value in self._token_to_value.items():
            restored = restored.replace(token, original_value)
        return restored

class AI_Functions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        self.ctx_menu = app_commands.ContextMenu(name="Translate to English", callback=self.translate_message)
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def execute_translation(self, text: str) -> Tuple[bool, str, str]:
        system_instruction = (
            "You are an accurate multilingual translator. "
            "Analyze the text: detect its primary language and determine if it is already in English. "
            "If it is already in English, set 'is_already_english' to true and leave 'translated_text' empty. "
            "If it is in another language, translate it into natural, fluent English. "
            "Always return pure valid JSON matching this schema:\n"
            '{"source_language": "string", "is_already_english": boolean, "translated_text": "string"}'
        )

        response = await self.ai_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"Text to translate:\n\n{text}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=1000,
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
        )

        data = json.loads(response.text or "{}")
        return (
            data.get("is_already_english", False),
            data.get("source_language", "Unknown"),
            data.get("translated_text", "")
        )

    async def fetch_preceding_context(self, channel: discord.abc.Messageable, message: discord.Message, limit: int = 3) -> str:
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return ""

        context_lines = []
        try:
            async for prev in channel.history(limit=limit, before=message):
                if prev.clean_content.strip() and not prev.author.bot:
                    context_lines.append(f"{prev.author.display_name}: {prev.clean_content.strip()}")
        except discord.DiscordException:
            return ""

        context_lines.reverse()
        return "\n".join(context_lines)

    IMAGE_TRANSLATION_SYSTEM_PROMPT = (
        "You are an accurate multimodal OCR and translator. "
        "Extract all visible text from the provided image, detect its primary language ('lang'), "
        "set 'is_en' to true if the text is already in English (otherwise false), "
        "and put the English translation in 'text' (or empty string if already in English)."
    )

    IMAGE_TRANSLATION_SCHEMA = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "is_en": types.Schema(type=types.Type.BOOLEAN),
            "lang": types.Schema(type=types.Type.STRING),
            "text": types.Schema(type=types.Type.STRING),
        },
        required=["is_en", "lang", "text"],
    )

    async def execute_image_translation(self, attachment: discord.Attachment):
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            raise ValueError("Attachment is not a valid image.")

        image_bytes = await attachment.read()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=attachment.content_type)

        try:
            response = await self.ai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=[image_part, "Extract all visible text from this image and translate it into English."],
                config=types.GenerateContentConfig(
                    system_instruction=self.IMAGE_TRANSLATION_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=self.IMAGE_TRANSLATION_SCHEMA,
                    temperature=0.0,
                    max_output_tokens=1000,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as e:
            raise RuntimeError(f"Gemini Vision error: {e}")

        data = json.loads(response.text or "{}")
        return (bool(data.get("is_en", False)), str(data.get("lang", "Unknown")).strip(), str(data.get("text", "")).strip())

    FILLER_WORDS = frozenset({
        "lol", "lmao", "rofl", "gg", "ggs", "k", "ok", "okay",
        "yes", "no", "yeah", "yep", "nope", "oof", "w", "l", "rip", "nice", "ty", "thx",
    })

    URL_COMPRESS_RE = re.compile(r"https?://([^\s/]+)\S*")

    SUMMARIZE_SYSTEM_PROMPT = (
        "Summarize the Discord chat transcript into high-signal bullet points.\n"
        "Rules:\n"
        "1. Group strictly under these headers (omit any empty section):\n"
        "### 📌 Key Takeaways & Decisions\n"
        "### 💬 Active Topics\n"
        "### ❓ Questions & Plans\n"
        "2. Use concise bullets with **bold lead-ins**.\n"
        "3. Preserve all bracketed tokens (such as [[USER_1]], [[EMAIL_1]]) verbatim when referencing "
        "participants or values; do not alter or translate token names.\n"
        "4. Ignore greetings and filler. Keep total output under 1,200 characters."
    )

    @app_commands.command(name="summarize", description="Summarize recent channel activity. Powered with AI")
    @app_commands.describe(channel="The channel to catch up on (defaults to current channel)", limit="Number of recent messages to analyze (10 to 200, default 100)", include_bots="Whether to include bot messages in the summary")
    @app_commands.guild_only()
    async def summarize(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, limit: app_commands.Range[int, 10, 200] = 100, include_bots: bool = False):
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("I can only summarize text channels and threads. :dog:", ephemeral=True)
            return

        bot_perms = target_channel.permissions_for(interaction.guild.me)
        if not bot_perms.read_messages or not bot_perms.read_message_history:
            await interaction.response.send_message(f"I lack permissions to read message history in {target_channel.mention}. :pleading_face:", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        cleaned_entries: list[tuple[str, str, discord.abc.Snowflake]] = []
        async for msg in target_channel.history(limit=limit, oldest_first=False):
            if not include_bots and msg.author.bot:
                continue

            content = msg.clean_content.strip()
            if not content or content.startswith(("/", "!", "?", ".")):
                continue

            if " " not in content and content.lower() in self.FILLER_WORDS:
                continue

            content = self.URL_COMPRESS_RE.sub(r"[link: \1]", content)

            if len(content) > 350:
                content = content[:347] + "..."

            cleaned_entries.append((msg.author.display_name, content, msg.created_at))

        if not cleaned_entries:
            await interaction.followup.send(
                f"⚠️ No readable text messages found in {target_channel.mention} within the last {limit} messages.",
                ephemeral=True,
            )
            return

        cleaned_entries.reverse()
        anonymizer = ReversibleAnonymizer()

        tokenized_entries = [(anonymizer.tokenize_author(author), anonymizer.tokenize_text(content), created_at) for author, content, created_at in cleaned_entries]

        analyzed_count = len(tokenized_entries)
        time_span = f"{tokenized_entries[0][2].strftime('%H:%M')} – {tokenized_entries[-1][2].strftime('%H:%M')} UTC"

        formatted_blocks = []
        current_author = None
        current_lines = []

        for author, text, _ in tokenized_entries:
            if author == current_author:
                current_lines.append(text)
            else:
                if current_author:
                    formatted_blocks.append(f"{current_author}: {' | '.join(current_lines)}")
                current_author = author
                current_lines = [text]

        if current_author and current_lines:
            formatted_blocks.append(f"{current_author}: {' | '.join(current_lines)}")

        transcript = "\n".join(formatted_blocks)
        if len(transcript) > 6000:
            transcript = transcript[-6000:]

        user_prompt = f"#{target_channel.name} ({analyzed_count} msgs):\n{transcript}"

        try:
            response = await self.ai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.SUMMARIZE_SYSTEM_PROMPT,
                    temperature=0.1,
                    max_output_tokens=1024,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as e:
            await interaction.followup.send(f"Gemini API error: `{e}`", ephemeral=True)
            return

        raw_summary = (response.text or "No summary could be generated.").strip()
        summary_text = anonymizer.restore(raw_summary)

        if len(summary_text) > 4000:
            summary_text = summary_text[:3990] + "\n\n*(Truncated due to length)*"

        embed = discord.Embed(
            title=f"📋 Catch-Up Summary for #{target_channel.name}",
            description=summary_text,
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Analyzed {analyzed_count} messages ({time_span})")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="translate", description="Translate text, an uploaded image, or an existing message into English. Powered by AI")
    @app_commands.describe(text="The text you want translated directly into English", image="Upload an image containing text to translate", message="A message link or message ID from this channel")
    @app_commands.guild_only()
    async def translate_command(self, interaction: discord.Interaction, text: Optional[str] = None, image: Optional[discord.Attachment] = None, message: Optional[str] = None):
        if not text and not image and not message:
            await interaction.response.send_message("Provide either `text`, an `image` attachment, or a `message` link/ID. :dog:", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        source_author = None
        source_jump_url = None
        source_image_url = None
        content_to_translate = ""
        target_image: Optional[discord.Attachment] = None

        if text:
            content_to_translate = text.strip()
        elif image:
            if not image.content_type or not image.content_type.startswith("image/"):
                await interaction.followup.send("The uploaded file must be an image (PNG, JPG, WebP). :dog:")
                return
            if image.size > 8 * 1024 * 1024:
                await interaction.followup.send("The image is too large (max 8MB). :pleading_face:")
                return

            target_image = image
            source_image_url = image.url
        elif message:
            target_msg: Optional[discord.Message] = None
            msg_str = message.strip()
            match = DISCORD_MSG_LINK_RE.match(msg_str)
            if match:
                channel_id = int(match.group("channel_id"))
                msg_id = int(match.group("message_id"))
                target_chan = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                if isinstance(target_chan, (discord.TextChannel, discord.Thread)):
                    try:
                        target_msg = await target_chan.fetch_message(msg_id)
                    except discord.NotFound:
                        target_msg = None
            elif msg_str.isdigit() and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                try:
                    target_msg = await interaction.channel.fetch_message(int(msg_str))
                except discord.NotFound:
                    target_msg = None

            if not target_msg:
                await interaction.followup.send("Could not find a message with that link or ID. :pleading_face:", ephemeral=True)
                return

            source_author = target_msg.author
            source_jump_url = target_msg.jump_url

            if target_msg.clean_content.strip():
                content_to_translate = target_msg.clean_content.strip()
            elif target_msg.attachments:
                for att in target_msg.attachments:
                    if att.content_type and att.content_type.startswith("image/"):
                        if att.size <= 8 * 1024 * 1024:
                            target_image = att
                            source_image_url = att.url
                            break

            if not content_to_translate and not target_image:
                await interaction.followup.send("No readable text or valid image attachments (under 8MB) found on that message. :dog:", ephemeral=True)
                return

        try:
            if target_image:
                is_english, source_lang, translated = (await self.execute_image_translation(target_image))
            else:
                is_english, source_lang, translated = await self.execute_translation(content_to_translate)
        except Exception as e:
            await interaction.followup.send(f"Translation error :pleading_face:: `{e}`")
            return

        if is_english:
            await interaction.followup.send(f"The provided {'image' if target_image else 'text'} is already in English (detected: `{source_lang}`).")
            return

        embed = discord.Embed(description=translated, color=discord.Color.teal(), timestamp=discord.utils.utcnow())

        if source_author:
            embed.set_author(name=f"{source_author.display_name} (Original: {source_lang})", icon_url=source_author.display_avatar.url)
        else:
            embed.set_author(name=f"Detected Language: {source_lang}")

        if source_image_url:
            embed.set_thumbnail(url=source_image_url)

        embed.set_footer(text=f"Requested by {interaction.user.display_name}")

        view = discord.ui.View()
        if source_jump_url:
            view.add_item(discord.ui.Button(label="Jump to Message", url=source_jump_url, style=discord.ButtonStyle.link))

        await interaction.followup.send(embed=embed, view=view if source_jump_url else discord.utils.MISSING)

    async def translate_message(self, interaction: discord.Interaction, message: discord.Message):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server. :dog:", ephemeral=True)
            return

        content = message.clean_content.strip()
        target_image: Optional[discord.Attachment] = None

        if not content and message.attachments:
            for att in message.attachments:
                if (att.content_type and att.content_type.startswith("image/") and att.size <= 8 * 1024 * 1024):
                    target_image = att
                    break

        if not content and not target_image:
            await interaction.response.send_message("This message has no text or supported image attachments to translate. :pleading_face:", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if target_image:
                is_already_english, source_lang, translated_text = (await self.execute_image_translation(target_image))
            else:
                is_already_english, source_lang, translated_text = (await self.execute_translation(content))
        except Exception as e:
            await interaction.followup.send(f"An error occurred while translating :pleading_face:: `{e}`", ephemeral=True)
            return

        if is_already_english:
            await interaction.followup.send(f"That message by **{message.author.display_name}** is already in English (detected: `{source_lang}`). :dog:", ephemeral=True)
            return

        embed = discord.Embed(description=translated_text, color=discord.Color.teal(), timestamp=discord.utils.utcnow())
        embed.set_author(name=f"{message.author.display_name} (Original: {source_lang})", icon_url=message.author.display_avatar.url)

        if target_image:
            embed.set_thumbnail(url=target_image.url)

        embed.set_footer(text=f"Requested by {interaction.user.display_name}")

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Jump to Message", url=message.jump_url, style=discord.ButtonStyle.link))

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    ASK_SYSTEM_PROMPT = (
        "You are a helpful, accurate, and concise AI assistant in a Discord server.\n"
        "Rules:\n"
        "1. Directly answer the question or prompt provided in the user's message.\n"
        "2. Use clean Markdown formatting (bullet points, bold text, and code blocks where appropriate).\n"
        "3. Skip unnecessary filler or meta-chatter. Keep the total response under 1,800 characters."
    )

    @app_commands.command(name="ask", description="Ask Sugar a question! Powered by AI")
    @app_commands.describe(question="The question to ask, or a message link/ID containing the question")
    @app_commands.guild_only()
    async def ask_command(self, interaction: discord.Interaction, question: str):
        msg_str = question.strip()
        if not msg_str:
            await interaction.response.send_message("Please provide a valid question or a message link/ID. :dog:", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        source_author = None
        source_jump_url = None
        question_text = ""

        target_msg: Optional[discord.Message] = None
        match = DISCORD_MSG_LINK_RE.match(msg_str)

        if match:
            channel_id = int(match.group("channel_id"))
            msg_id = int(match.group("message_id"))
            target_chan = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            if isinstance(target_chan, (discord.TextChannel, discord.Thread)):
                try:
                    target_msg = await target_chan.fetch_message(msg_id)
                except discord.NotFound:
                    target_msg = None
            if not target_msg:
                await interaction.followup.send("Could not find a message with that link. :pleading_face:", ephemeral=True)
                return
        elif (msg_str.isdigit() and len(msg_str) >= 17 and isinstance(interaction.channel, (discord.TextChannel, discord.Thread))):
            try:
                target_msg = await interaction.channel.fetch_message(int(msg_str))
            except discord.NotFound:
                target_msg = None
            if not target_msg:
                await interaction.followup.send("Could not find a message with that ID in this channel. :pleading_face:", ephemeral=True)
                return

        if target_msg:
            question_text = target_msg.clean_content.strip()
            if not question_text:
                await interaction.followup.send("The referenced message does not contain any readable text. :pleading_face:", ephemeral=True)
                return
            source_author = target_msg.author
            source_jump_url = target_msg.jump_url
        else:
            question_text = msg_str

        try:
            response = await self.ai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=question_text,
                config=types.GenerateContentConfig(
                    system_instruction=self.ASK_SYSTEM_PROMPT,
                    temperature=0.3,
                    max_output_tokens=1024,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as e:
            await interaction.followup.send(f"Gemini API error: `{e}`", ephemeral=True)
            return

        answer_text = (response.text or "No answer could be generated.").strip()
        if len(answer_text) > 4000:
            answer_text = answer_text[:3990] + "\n\n*(Truncated due to length)*"

        embed = discord.Embed(description=answer_text, color=discord.Color.blurple(), timestamp=discord.utils.utcnow())

        if source_author:
            embed.set_author(name=f"Question from {source_author.display_name}", icon_url=source_author.display_avatar.url)
        else:
            embed.set_author(name=f"Question from {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        preview_q = (question_text if len(question_text) <= 250 else question_text[:247] + "...")
        embed.add_field(name="Question answered:", value=f"> {preview_q}", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")

        view = discord.ui.View()
        if source_jump_url:
            view.add_item(discord.ui.Button(label="Jump to Message", url=source_jump_url, style=discord.ButtonStyle.link))

        await interaction.followup.send(embed=embed, view=view if source_jump_url else discord.utils.MISSING, ephemeral=False)

    TRIVIA_SYSTEM_PROMPT = (
        "You are an engaging trivia quizmaster. Generate multiple-choice trivia questions based on the requested categories.\n"
        "Rules:\n"
        "1. Each question must have exactly 1 unambiguously correct answer ('ans') and 3 plausible but incorrect answers ('wrong').\n"
        "2. Keep questions clear and answers concise (under 60 characters each).\n"
        "3. Vary the difficulty and topics across the requested categories.\n"
        "4. Output strictly valid JSON matching the schema."
    )

    TRIVIA_RESPONSE_SCHEMA = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "questions": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "cat": types.Schema(type=types.Type.STRING),
                        "q": types.Schema(type=types.Type.STRING),
                        "ans": types.Schema(type=types.Type.STRING),
                        "wrong": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.STRING),
                        ),
                    },
                    required=["cat", "q", "ans", "wrong"],
                ),
            )
        },
        required=["questions"],
    )

    async def generate_trivia_questions(self, count: int, categories: str) -> list[dict]:
        user_prompt = (f"Generate {count} unique multiple-choice trivia questions.\nCategories: {categories}")

        try:
            response = await self.ai_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.TRIVIA_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=self.TRIVIA_RESPONSE_SCHEMA,
                    temperature=0.7,
                    max_output_tokens=min(4096, max(512, count * 220)),
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")

        data = json.loads(response.text or "{}")
        questions = data.get("questions", [])

        valid_questions = [q for q in questions if q.get("q") and q.get("ans") and len(q.get("wrong", [])) >= 3]
        return valid_questions[:count]

    @app_commands.command(name="aitrivia", description="Start an AI-generated trivia game.")
    @app_commands.describe(questions="Number of questions to play (1 to 10, default: 5)", categories="One or more categories separated by commas (e.g. 'Science, Gaming, History')")
    @app_commands.guild_only()
    async def trivia_command(self, interaction: discord.Interaction, questions: app_commands.Range[int, 1, 10] = 5, categories: str = "General Knowledge"):
        clean_categories = categories.strip() or "General Knowledge"

        await interaction.response.defer(ephemeral=True)

        try:
            question_list = await self.generate_trivia_questions(questions, clean_categories)
        except Exception as e:
            await interaction.followup.send(f"Failed to generate trivia questions: `{e}`", ephemeral=True)
            return

        if not question_list:
            await interaction.followup.send("Could not generate valid trivia questions for those categories. Please try again. :dog:", ephemeral=True)
            return

        view = TriviaView(user=interaction.user, categories=clean_categories, questions=question_list, points_per_question=1)
        initial_embed = view.build_question_embed()

        msg = await interaction.followup.send(embed=initial_embed, view=view, ephemeral=True)
        view.message = msg

class TriviaView(discord.ui.View):
    OPTION_LABELS = ("A", "B", "C", "D")

    def __init__(self, user: discord.abc.User, categories: str, questions: list[dict], points_per_question: int = 1):
        super().__init__(timeout=300)
        self.user = user
        self.categories = categories
        self.questions = questions
        self.points_per_question = points_per_question

        self.current_index = 0
        self.correct_count = 0
        self.current_options: list[str] = []
        self.correct_answer: str = ""
        self.message: Optional[discord.WebhookMessage] = None

        self._setup_current_question()

    def _setup_current_question(self):
        self.clear_items()
        q_data = self.questions[self.current_index]
        self.correct_answer = str(q_data["ans"]).strip()

        wrong_list = [str(w).strip() for w in q_data.get("wrong", [])[:3]]
        self.current_options = [self.correct_answer] + wrong_list
        random.shuffle(self.current_options)

        for idx, option_text in enumerate(self.current_options):
            label_letter = self.OPTION_LABELS[idx]
            btn_label = f"{label_letter}: {option_text}"
            if len(btn_label) > 80:
                btn_label = btn_label[:77] + "..."

            button = discord.ui.Button(label=btn_label, style=discord.ButtonStyle.secondary, custom_id=f"trivia_opt_{idx}", row=idx // 2)
            button.callback = self._make_callback(option_text)
            self.add_item(button)

    def build_question_embed(self, feedback: Optional[str] = None):
        q_data = self.questions[self.current_index]
        total = len(self.questions)
        current_points = self.correct_count * self.points_per_question

        choices_formatted = "\n".join(f"**{self.OPTION_LABELS[i]}.** {opt}" for i, opt in enumerate(self.current_options))

        desc_parts = []
        if feedback:
            desc_parts.append(f"{feedback}\n")
        desc_parts.append(f"**{q_data['q']}**\n\n{choices_formatted}")

        embed = discord.Embed(title=f"🧠 Trivia — Question {self.current_index + 1} of {total}", description="\n".join(desc_parts), color=discord.Color.blurple())
        embed.add_field(name="Category", value=str(q_data.get("cat", self.categories)), inline=True)
        embed.add_field(name="Current Score", value=f"**{current_points}** pts ({self.correct_count}/{self.current_index})", inline=True)
        embed.set_footer(text="Select an answer below • Only you can see this game")
        return embed

    def _make_callback(self, selected_option: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("This isn't your trivia session!", ephemeral=True)
                return

            is_correct = selected_option == self.correct_answer
            if is_correct:
                self.correct_count += 1
                feedback = f"✅ **Correct!** (+{self.points_per_question} pts)"
            else:
                feedback = (f"❌ **Wrong!** The correct answer was: **{self.correct_answer}**")

            self.current_index += 1

            if self.current_index < len(self.questions):
                self._setup_current_question()
                next_embed = self.build_question_embed(feedback=feedback)
                await interaction.response.edit_message(embed=next_embed, view=self)
            else:
                self.stop()
                total_q = len(self.questions)
                total_points = self.correct_count * self.points_per_question
                max_points = total_q * self.points_per_question
                accuracy = round((self.correct_count / total_q) * 100)

                private_end_embed = discord.Embed(
                    title="🏁 Trivia Completed!",
                    description=(
                        f"{feedback}\n\n"
                        f"You answered **{self.correct_count}/{total_q}** correctly and earned **{total_points} points**!\n"
                        f"Your final scoreboard has been posted publicly in the channel."
                    ),
                    color=discord.Color.green(),
                )
                await interaction.response.edit_message(embed=private_end_embed, view=None)

                public_embed = discord.Embed(title="🏆 Trivia Results!", description=f"{self.user.mention} just finished a trivia challenge!", color=discord.Color.gold(), timestamp=discord.utils.utcnow())
                public_embed.set_author(name=self.user.display_name, icon_url=self.user.display_avatar.url)
                public_embed.add_field(name="Categories", value=self.categories, inline=False)
                public_embed.add_field(name="Correct Answers", value=f"**{self.correct_count} / {total_q}** ({accuracy}%)", inline=True)
                public_embed.add_field(name="Points Obtained", value=f"**{total_points}** / {max_points} pts", inline=True)

                await interaction.followup.send(embed=public_embed, ephemeral=False)

        return callback

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="**Trivia session timed out due to inactivity.**", view=self)
            except discord.DiscordException:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(AI_Functions(bot))