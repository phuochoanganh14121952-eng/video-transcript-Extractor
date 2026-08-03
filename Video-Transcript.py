import os
import json
import streamlit as st
import whisper
from google import genai
from google.genai import types

st.set_page_config(page_title="Video_Transcript", layout="wide")

HISTORY_FILE = "video_transcript_history.json"

def save_history_to_disk(history_data):
    try:
        light_history = []
        for item in history_data:
            light_item = {
                "title": item.get("title"),
                "filename": item.get("filename"),
                "summary_en": item.get("summary_en"),
                "summary_vi": item.get("summary_vi"),
                "chat_messages": item.get("chat_messages", []),
                "segments": item.get("segments", [])
            }
            light_history.append(light_item)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(light_history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_history_from_disk():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

if "history" not in st.session_state:
    st.session_state.history = load_history_from_disk()
if "current_transcript_data" not in st.session_state:
    st.session_state.current_transcript_data = None

with st.sidebar:
    st.header("🔑 Cấu hình API")
    user_api_key = st.text_input(
        "Nhập Gemini API Key:",
        type="password",
        help="Lấy API key từ Google AI Studio"
    )
    
    client = None
    if user_api_key:
        try:
            client = genai.Client(api_key=user_api_key)
            st.success("✅ Đã kết nối API Key")
        except Exception as e:
            st.error(f"Lỗi khởi tạo API: {e}")
    else:
        st.warning("⚠️ Vui lòng nhập API Key để sử dụng ứng dụng.")

    st.divider()
    st.header("📚 Lịch sử bài học")
    
    if st.session_state.history:
        if st.button("🗑️ Xóa toàn bộ lịch sử", use_container_width=True):
            st.session_state.history = []
            st.session_state.current_transcript_data = None
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            st.rerun()

        for idx, hist in enumerate(st.session_state.history):
            col_h1, col_h2 = st.columns([4, 1])
            with col_h1:
                if st.button(f"📄 {hist['title']}", key=f"hist_btn_{idx}", use_container_width=True):
                    st.session_state.current_transcript_data = hist
                    st.rerun()
            with col_h2:
                if st.button("❌", key=f"del_{idx}", help="Xóa bài này"):
                    st.session_state.history.pop(idx)
                    save_history_to_disk(st.session_state.history)
                    if st.session_state.current_transcript_data and st.session_state.current_transcript_data.get("filename") == hist.get("filename"):
                        st.session_state.current_transcript_data = None
                    st.rerun()
    else:
        st.caption("Chưa có lịch sử nào được lưu.")

st.title("🎙️ Video_Transcript")

if not user_api_key or client is None:
    st.info("Vui lòng nhập Gemini API Key ở thanh bên (Sidebar) để tiếp tục.")
    st.stop()

@st.cache_resource
def load_whisper_model():
    return whisper.load_model("small")

model = load_whisper_model()

uploaded_file = st.file_uploader("Tải lên file âm thanh hoặc video", type=["mp3", "wav", "m4a", "mp4"])

if uploaded_file:
    if (st.session_state.current_transcript_data is None) or (st.session_state.current_transcript_data.get("filename") != uploaded_file.name):
        
        existing_item = next((h for h in st.session_state.history if h["filename"] == uploaded_file.name), None)
        
        if existing_item:
            st.session_state.current_transcript_data = existing_item
        else:
            import tempfile
            from pydub import AudioSegment

            with tempfile.TemporaryDirectory() as temp_dir:
                input_path = os.path.join(temp_dir, uploaded_file.name)
                with open(input_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                with st.spinner("1/3. Whisper đang ngắt từng phân đoạn thoại..."):
                    raw_result = model.transcribe(
                        input_path,
                        language="en",
                        temperature=0.0,
                        condition_on_previous_text=False,
                        no_speech_threshold=0.1
                    )
                    raw_segments = raw_result.get("segments", [])

                sentences = [s['text'].strip() for s in raw_segments]

                with st.spinner("2/3. Gemini đang gán người nói và dịch thuật..."):
                    prompt = f"""
Dưới đây là danh sách các câu thoại tách theo mốc thời gian:
{json.dumps(sentences, ensure_ascii=False, indent=2)}

Nhiệm vụ:
1. Dịch từng câu sang tiếng Việt.
2. Gán Speaker A hoặc Speaker B cho từng câu (luân phiên người nói theo ngữ cảnh).
3. Tóm tắt nội dung bài học bằng tiếng Anh và tiếng Việt.

Trả về duy nhất định dạng JSON thuần túy (không kèm markdown như ```json) với cấu trúc sau:
{{
  "summary_en": "Tóm tắt chi tiết nội dung bài học bằng tiếng Anh",
  "summary_vi": "Tóm tắt chi tiết nội dung bài học bằng tiếng Việt",
  "items": [
    {{
      "speaker": "Speaker A",
      "english": "Nội dung câu",
      "vietnamese": "Dịch tiếng Việt câu"
    }}
  ]
}}
Lưu ý: Số lượng phần tử trong mảng `items` phải ĐÚNG BẰNG số lượng câu thoại đầu vào ({len(sentences)}).
"""
                    try:
                        response = client.models.generate_content(
                            model='gemini-3.6-flash',
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json"
                            ),
                        )
                        clean_text = response.text.strip()
                        if clean_text.startswith("```"):
                            clean_text = clean_text.split("```")[1]
                            if clean_text.startswith("json"):
                                clean_text = clean_text[4:]
                        res_json = json.loads(clean_text.strip())
                        items = res_json.get("items", [])
                    except Exception:
                        res_json = {}
                        items = []

                sum_en = res_json.get("summary_en", "").strip()
                sum_vi = res_json.get("summary_vi", "").strip()
                if not sum_en or not sum_vi:
                    full_text_joined = " ".join(sentences)
                    sum_en = f"Dialogue discussion covering: {full_text_joined[:150]}..."
                    sum_vi = f"Nội dung hội thoại trao đổi về: {full_text_joined[:150]}..."

                audio_segment = AudioSegment.from_file(input_path)
                segments_data = []
                
                for idx, seg in enumerate(raw_segments):
                    start_ms = max(0, int(seg["start"] * 1000) - 100)
                    end_ms = int(seg["end"] * 1000)
                    chunk = audio_segment[start_ms:end_ms]
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_chunk:
                        chunk.export(tmp_chunk.name, format="mp3")
                        tmp_chunk_path = tmp_chunk.name
                    with open(tmp_chunk_path, "rb") as cf:
                        chunk_bytes = cf.read()
                    try:
                        os.unlink(tmp_chunk_path)
                    except Exception:
                        pass

                    speaker_label = items[idx]["speaker"] if idx < len(items) else f"Speaker {idx+1}"
                    text_en = seg["text"].strip()
                    text_vi = items[idx]["vietnamese"] if idx < len(items) else ""
                    
                    import base64
                    b64_audio = base64.b64encode(chunk_bytes).decode('utf-8')

                    segments_data.append({
                        "speaker": speaker_label,
                        "english": text_en,
                        "vietnamese": text_vi,
                        "audio_b64": b64_audio
                    })

                with open(input_path, "rb") as vf:
                    video_bytes = vf.read()
                
                import base64
                b64_video = base64.b64encode(video_bytes).decode('utf-8')

                new_history_item = {
                    "title": uploaded_file.name,
                    "filename": uploaded_file.name,
                    "video_b64": b64_video,
                    "summary_en": sum_en,
                    "summary_vi": sum_vi,
                    "segments": segments_data,
                    "chat_messages": []
                }

                st.session_state.history.insert(0, new_history_item)
                save_history_to_disk(st.session_state.history)
                st.session_state.current_transcript_data = new_history_item

if st.session_state.current_transcript_data:
    data = st.session_state.current_transcript_data

    st.subheader(f"📺 Video bài học: {data['title']}")
    if "video_b64" in data and data["video_b64"]:
        import base64
        video_bytes_decoded = base64.b64decode(data["video_b64"])
        st.video(video_bytes_decoded)
    st.divider()

    st.subheader("📝 Tóm tắt bài học")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**English Summary:**\n{data.get('summary_en', 'Đang cập nhật tóm tắt...')}")
    with col2:
        st.markdown(f"**Tóm tắt tiếng Việt:**\n{data.get('summary_vi', 'Đang cập nhật tóm tắt...')}")

    st.divider()
    st.subheader("🗣️ Chi tiết lượt thoại & Phát âm")

    for seg in data["segments"]:
        c1, c2, c3 = st.columns([1.2, 4.8, 3.0])
        with c1:
            st.markdown(f"**{seg['speaker']}**")
        with c2:
            st.markdown(f"{seg['english']}")
            st.caption(f"{seg['vietnamese']}")
        with c3:
            if "audio_b64" in seg and seg["audio_b64"]:
                import base64
                audio_bytes_decoded = base64.b64decode(seg["audio_b64"])
                st.audio(audio_bytes_decoded, format="audio/mp3")

    st.divider()
    st.subheader("🤖 AI Companion - Trợ lý giải đáp nội dung video")
    st.caption("Hỏi đáp sâu hơn về từ vựng, ngữ pháp hoặc nội dung của bài học này.")

    if "chat_messages" not in data:
        data["chat_messages"] = []

    for message in data["chat_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Nhập câu hỏi về bài học (ví dụ: Giải thích ngữ pháp câu số 2...)"):
        data["chat_messages"].append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.spinner("AI Companion đang phân tích và trả lời..."):
            clean_segments_for_ai = [{"speaker": s["speaker"], "english": s["english"], "vietnamese": s["vietnamese"]} for s in data["segments"]]
            full_context = f"Tóm tắt: {data.get('summary_en', '')}\nCác câu thoại:\n" + json.dumps(clean_segments_for_ai, ensure_ascii=False)
            
            try:
                chat = client.chats.create(
                    model="gemini-3.6-flash",
                    config=types.GenerateContentConfig(
                        system_instruction="Bạn là một trợ lý AI chuyên gia tiếng Anh. Hãy giải đáp thắc mắc của người học dựa trực tiếp vào nội dung bài học được cung cấp."
                    )
                )
                chat.send_message(f"Ngữ cảnh bài học:\n{full_context}")
                response = chat.send_message(user_query)
                ai_reply = response.text
            except Exception as e:
                ai_reply = f"Lỗi phản hồi từ AI Companion: {e}"

        data["chat_messages"].append({"role": "assistant", "content": ai_reply})
        save_history_to_disk(st.session_state.history)
        with st.chat_message("assistant"):
            st.markdown(ai_reply)
