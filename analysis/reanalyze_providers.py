from __future__ import annotations

import json
import time
from pathlib import Path


from log_manager import LogManager
from reanalyze_logger import get_logger




class ReanalyzeProvidersMixin:
    def _reanalyze_yolo_objects_with_gpt55(self, folder: Path, data: dict, image_path: Path) -> dict:
        t0 = time.time()
        logger = get_logger()
        prompt = ""
        raw = ""
        used_model = ""
        user_intent = ""
        try:
            from llm_client import QwenVLClient

            prompt, width, height, vision_width, vision_height, scale_x, scale_y, click_x, click_y, scene_text = \
                self._build_reanalyze_prompt(image_path, data)

            debug_dir = folder / "gpt55_reanalyze"
            debug_dir.mkdir(parents=True, exist_ok=True)
            request_payload = {
                "model": "openai/gpt-5.5",
                "image_path": str(image_path),
                "original_image_size": [width, height],
                "vision_image_size": [vision_width, vision_height],
                "scale_to_original": [scale_x, scale_y],
                "click_point": [click_x, click_y],
                "scene_text": scene_text,
                "prompt": prompt,
            }
            (debug_dir / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            LogManager().append(
                "[GPT-5.5 Reanalyze] request\n"
                f"  image={image_path}\n"
                f"  original_size={width}x{height}\n"
                f"  vision_size={vision_width}x{vision_height}\n"
                f"  scale_to_original=({scale_x:.6f},{scale_y:.6f})\n"
                f"  click=({click_x},{click_y})\n"
                f"  prompt_file={debug_dir / 'prompt.txt'}\n"
                f"{prompt}"
            )
            client = QwenVLClient(model="openai/gpt-5.5")
            image_b64 = client._prepare_image(image_path)
            models = [client.model] + [m for m in client.FALLBACK_MODELS if m != client.model]
            raw = ""
            errors = []
            for model in models:
                try:
                    LogManager().append(f"[GPT-5.5 Reanalyze] calling model={model} max_tokens=4096")
                    raw = client._call_vision_api(model, image_b64, prompt, 4096, 180)
                    LogManager().append(f"[GPT-5.5 Reanalyze] model={model} raw_len={len(raw)}")
                    if raw.strip():
                        used_model = model
                        break
                    errors.append(f"{model}: empty response")
                except Exception as call_error:
                    errors.append(f"{model}: {call_error}")
                    LogManager().append(f"[GPT-5.5 Reanalyze] model={model} failed: {call_error}")
            if not raw.strip():
                error_text = "\n".join(errors) or "empty response"
                (debug_dir / "response_error.txt").write_text(error_text, encoding="utf-8")
                LogManager().append(f"[GPT-5.5 Reanalyze] all models failed/empty\n{error_text}")
                duration_ms = (time.time() - t0) * 1000
                logger.append(
                    image_path=str(image_path),
                    folder=str(folder),
                    prompt=prompt,
                    raw_response="",
                    model=", ".join(models),
                    objects=[],
                    error=error_text,
                    duration_ms=duration_ms,
                    metadata={"debug_dir": str(debug_dir)},
                )
                return {"error": error_text, "objects": []}
            (debug_dir / "response_raw.txt").write_text(raw, encoding="utf-8")
            LogManager().append(
                "[GPT-5.5 Reanalyze] raw response\n"
                f"  response_file={debug_dir / 'response_raw.txt'}\n"
                f"{raw}"
            )
            objects, user_intent = self._process_reanalyze_response(raw, width, height, scale_x, scale_y, click_x, click_y)
            for obj in objects:
                obj["source"] = "gpt-5.5-reanalyze"
            parsed_payload = {
                "objects": objects,
                "object_count": len(objects),
            }
            (debug_dir / "parsed_objects.json").write_text(
                json.dumps(parsed_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            LogManager().append(
                "[GPT-5.5 Reanalyze] parsed objects\n"
                f"  parsed_file={debug_dir / 'parsed_objects.json'}\n"
                f"{json.dumps(parsed_payload, ensure_ascii=False, indent=2)}"
            )
            duration_ms = (time.time() - t0) * 1000
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model or "openai/gpt-5.5",
                objects=objects,
                error="",
                duration_ms=duration_ms,
                metadata={
                    "debug_dir": str(debug_dir),
                    "original_size": [width, height],
                    "vision_size": [vision_width, vision_height],
                    "click_point": [click_x, click_y],
                    "user_intent": user_intent,
                },
            )
            return {"objects": objects, "raw": raw[:1200], "user_intent": user_intent}
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            error_str = str(e)
            LogManager().append(f"[Audit] GPT-5.5 reanalyze failed: {e}")
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model or "openai/gpt-5.5",
                objects=[],
                error=error_str,
                duration_ms=duration_ms,
                metadata={},
            )
            return {"error": error_str, "objects": []}

    def _reanalyze_yolo_objects_with_qwen_vl_max(self, folder: Path, data: dict, image_path: Path) -> dict:
        """使用阿里云 DashScope qwen-vl-max 进行 Reanalyze。"""
        t0 = time.time()
        logger = get_logger()
        prompt = ""
        raw = ""
        used_model = "qwen-vl-max"
        user_intent = ""
        try:
            from llm_client import DashScopeVLClient

            prompt, width, height, vision_width, vision_height, scale_x, scale_y, click_x, click_y, scene_text = \
                self._build_reanalyze_prompt(image_path, data)

            debug_dir = folder / "qwen_vl_reanalyze"
            debug_dir.mkdir(parents=True, exist_ok=True)
            request_payload = {
                "model": "qwen-vl-max",
                "image_path": str(image_path),
                "original_image_size": [width, height],
                "vision_image_size": [vision_width, vision_height],
                "scale_to_original": [scale_x, scale_y],
                "click_point": [click_x, click_y],
                "scene_text": scene_text,
                "prompt": prompt,
            }
            (debug_dir / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (debug_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            LogManager().append(
                "[Qwen-VL Reanalyze] request\n"
                f"  image={image_path}\n"
                f"  original_size={width}x{height}\n"
                f"  vision_size={vision_width}x{vision_height}\n"
                f"  scale_to_original=({scale_x:.6f},{scale_y:.6f})\n"
                f"  click=({click_x},{click_y})\n"
                f"  prompt_file={debug_dir / 'prompt.txt'}\n"
                f"{prompt}"
            )
            client = DashScopeVLClient()
            if not client.is_ready():
                return {"error": "DASHSCOPE_API_KEY not configured", "objects": []}
            raw = client.call_vision(image_path, prompt, max_tokens=4096, timeout=180)
            if raw.startswith("[dashscope_vl_error]"):
                (debug_dir / "response_error.txt").write_text(raw, encoding="utf-8")
                LogManager().append(f"[Qwen-VL Reanalyze] failed: {raw}")
                duration_ms = (time.time() - t0) * 1000
                logger.append(
                    image_path=str(image_path),
                    folder=str(folder),
                    prompt=prompt,
                    raw_response="",
                    model=used_model,
                    objects=[],
                    error=raw,
                    duration_ms=duration_ms,
                    metadata={"debug_dir": str(debug_dir)},
                )
                return {"error": raw, "objects": []}
            (debug_dir / "response_raw.txt").write_text(raw, encoding="utf-8")
            LogManager().append(
                "[Qwen-VL Reanalyze] raw response\n"
                f"  response_file={debug_dir / 'response_raw.txt'}\n"
                f"{raw}"
            )
            objects, user_intent = self._process_reanalyze_response(raw, width, height, scale_x, scale_y, click_x, click_y)
            for obj in objects:
                obj["source"] = "qwen-vl-max-reanalyze"
            parsed_payload = {
                "objects": objects,
                "object_count": len(objects),
            }
            (debug_dir / "parsed_objects.json").write_text(
                json.dumps(parsed_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            LogManager().append(
                "[Qwen-VL Reanalyze] parsed objects\n"
                f"  parsed_file={debug_dir / 'parsed_objects.json'}\n"
                f"{json.dumps(parsed_payload, ensure_ascii=False, indent=2)}"
            )
            duration_ms = (time.time() - t0) * 1000
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model,
                objects=objects,
                error="",
                duration_ms=duration_ms,
                metadata={
                    "debug_dir": str(debug_dir),
                    "original_size": [width, height],
                    "vision_size": [vision_width, vision_height],
                    "click_point": [click_x, click_y],
                    "user_intent": user_intent,
                },
            )
            return {"objects": objects, "raw": raw[:1200], "user_intent": user_intent}
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            error_str = str(e)
            LogManager().append(f"[Audit] Qwen-VL reanalyze failed: {e}")
            logger.append(
                image_path=str(image_path),
                folder=str(folder),
                prompt=prompt,
                raw_response=raw,
                model=used_model,
                objects=[],
                error=error_str,
                duration_ms=duration_ms,
                metadata={},
            )
            return {"error": error_str, "objects": []}

