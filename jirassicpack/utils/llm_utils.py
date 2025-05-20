"""
llm_utils.py

Shared utilities for LLM-based ticket grouping and prompt construction.
"""
import json
from concurrent.futures import as_completed

def build_llm_manager_prompt(params, example_categories, prompt_examples):
    """Build the LLM prompt for manager-focused ticket categorization."""
    preferred_categories = params.get('preferred_categories') if params else None
    manager_prompt = (
        "You are an expert Jira ticket analyst. Your goal is to help a manager quickly understand the main types of work being done.\n"
        "Given the following list of tickets (with key, summary, and description), group them into a small number (ideally 5-10) of broad, manager-friendly categories. Each category should be:\n"
        "- Actionable and meaningful to a manager (e.g., " + ', '.join(f'\"{cat}\"' for cat in example_categories) + ").\n"
        "- Based on the type of work being done (e.g., running scripts, exporting data, updating configurations, resolving user issues) or who the work is being done for (e.g., a specific client or department).\n"
        "- Avoid generic categories like 'Other' or 'Miscellaneous' unless absolutely necessary, and never use them for more than 10% of tickets.\n"
        "- If a ticket could fit in more than one category, choose the one that would be most useful for a manager's report.\n"
    )
    if preferred_categories:
        manager_prompt += ("- Where possible, use one of these preferred categories: " + ', '.join(f'\"{cat}\"' for cat in preferred_categories) + ".\n")
    manager_prompt += "Return a JSON object mapping each ticket key to its category. Do not include any extra text, comments, or explanations—just output the JSON object. STRICT: Output ONLY valid JSON, no prose, no comments, no markdown.\n"
    manager_prompt += prompt_examples
    return manager_prompt

def chunk_tickets(tickets, chunk_size):
    """Yield successive chunks from the tickets list."""
    for i in range(0, len(tickets), chunk_size):
        yield tickets[i:i+chunk_size]

def call_llm_for_chunks(chunk_prompts, use_async, llm_utils, response_format, executor):
    """Call the LLM for each chunk, using async or threaded execution."""
    chunk_results = []
    if use_async:
        async def process_all_chunks_async(chunk_prompts):
            import asyncio
            tasks = [
                llm_utils.call_openai_llm_async(llm_prompt, response_format=response_format)
                for _, llm_prompt in chunk_prompts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [(chunk_keys, result) for (chunk_keys, _), result in zip(chunk_prompts, results)]
        import asyncio
        loop = asyncio.get_event_loop()
        chunk_results = loop.run_until_complete(process_all_chunks_async(chunk_prompts))
    else:
        chunk_futures = [executor.submit(llm_utils.call_openai_llm, llm_prompt, response_format=response_format) for chunk_keys, llm_prompt in chunk_prompts]
        for (chunk_keys, _), future in zip(chunk_prompts, as_completed(chunk_futures)):
            try:
                llm_response = future.result()
                chunk_results.append((chunk_keys, llm_response))
            except Exception as e:
                chunk_results.append((chunk_keys, None))
    return chunk_results

def parse_llm_chunk_results(chunk_results, chunk_prompts, superbatch, logger):
    """Parse LLM responses for each chunk, log/print diagnostics, and collect results."""
    results = {}
    failed_chunks = []
    chunk_prompt_map = {tuple(keys): prompt for keys, prompt in chunk_prompts}
    for chunk_keys, llm_response in chunk_results:
        llm_prompt = chunk_prompt_map.get(tuple(chunk_keys), "<prompt not found>")
        logger('info', f"[summarize_tickets] Sending LLM prompt for chunk {chunk_keys}: {llm_prompt[:500]}")
        print(f"[summarize_tickets] Sending LLM prompt for chunk {chunk_keys}: {llm_prompt[:500]}")
        logger('info', f"[summarize_tickets] Raw LLM response for chunk {chunk_keys}: {repr(llm_response)[:1000]}")
        print(f"[summarize_tickets] Raw LLM response for chunk {chunk_keys}: {repr(llm_response)[:1000]}")
        if not llm_response or not isinstance(llm_response, str):
            logger('error', f"[summarize_tickets] LLM response is empty or not a string for chunk {chunk_keys}: {repr(llm_response)}")
            failed_chunks.append([tc for tc in superbatch if tc['key'] in chunk_keys])
            continue
        try:
            chunk_result = json.loads(llm_response)
            results.update({k.strip().upper(): v for k, v in chunk_result.items()})
        except Exception:
            failed_chunks.append([tc for tc in superbatch if tc['key'] in chunk_keys])
    return results, failed_chunks

def llm_group_tickets(ticket_contexts, params, use_async, chunk_sizes, manager_prompt, executor, logger):
    """Main LLM grouping logic: chunk tickets, call LLM, parse results, retry failed chunks with smaller sizes."""
    import jirassicpack.utils.llm as llm_utils
    response_format = {"type": "json_object"}
    superbatch = ticket_contexts
    results = {}
    for chunk_size in chunk_sizes:
        chunk_prompts = []
        for chunk in chunk_tickets(superbatch, chunk_size):
            chunk_keys = [t['key'] for t in chunk]
            llm_prompt = manager_prompt + f"Tickets: {json.dumps(chunk)}"
            chunk_prompts.append((chunk_keys, llm_prompt))
        chunk_results = call_llm_for_chunks(chunk_prompts, use_async, llm_utils, response_format, executor)
        for (chunk_keys, llm_response) in chunk_results:
            print(f"[summarize_tickets][DIAG] Processed chunk keys: {chunk_keys}")
            print(f"[summarize_tickets][DIAG] Chunk result: {llm_response}")
            logger('info', f"[summarize_tickets][DIAG] Processed chunk keys: {chunk_keys}")
            logger('info', f"[summarize_tickets][DIAG] Chunk result: {llm_response}")
        chunk_results_parsed, failed_chunks = parse_llm_chunk_results(chunk_results, chunk_prompts, superbatch, logger)
        # Merging logic: accumulate all mappings
        results.update(chunk_results_parsed)
        if not failed_chunks:
            break
        else:
            superbatch = [tc for chunk in failed_chunks for tc in chunk]
    # Any still-failed tickets get Uncategorized, but only if not already present
    for tc in superbatch:
        key = tc['key'].strip().upper()
        if key not in results:
            results[key] = "Uncategorized"
            print(f"[llm_group_tickets][PATCH] Fallback: assigning {key} to 'Uncategorized'")
            logger('warning', f"[llm_group_tickets][PATCH] Fallback: assigning {key} to 'Uncategorized'")
    print(f"[summarize_tickets][DIAG] Final merged results: {list(results.items())[:10]}")
    logger('info', f"[summarize_tickets][DIAG] Final merged results: {list(results.items())[:10]}")
    return results 