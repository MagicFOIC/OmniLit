Terminology glossary format (bidirectional)

1. CSV/TSV files keep two columns: source,target. TXT/Markdown files may use source => target.
2. English -> Chinese uses source => target, for example large language model => ?????.
3. Chinese -> English automatically applies the same row in reverse as target => source, for example ????? => large language model.
4. Custom glossaries do not need duplicate reverse files; keep one source,target file for both directions.
5. On startup, OmniLit appends missing built-in default terms to existing built-in glossary files, but it does not delete or overwrite user custom files or user-added rows.
6. For formal translation, use the general academic glossary plus the current discipline glossary to reduce cross-domain mistranslation.
7. In AI/LLM papers, LLM/LLMs stay in English; Agent/Agents should be translated as ??? in the AI-agent context.
