import os
import io
import json
import tempfile
import zipfile
import streamlit as st
from faster_whisper import WhisperModel
from google import genai
from moviepy.editor import VideoFileClip, AudioFileClip
st.set_page_config(page_title="Video Transcript & AI Companion", layout="wide")

DB_FILE = "history_db.json"
MEDIA_DIR = "saved_media"

if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)

def load_history_from_disk():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history_to_disk(history_data):
    clean_history = []
    for item in history_data:
        clean_item = {
            "id": item.get("id"),
            "title": item["title"],
            "file_type": item.get("file_type", ""),
            "media_path": item.get("media_path", ""),
            "summary_en": item.get("summary_en", ""),
            "summary_vi": item.get("summary_vi", ""),
            "chat_history": item.get("chat_history", []),
            "data": [
                {
                    "speaker": row.get("speaker", ""),
                    "english": row.get("english", ""),
                    "vietnamese": row.get("vietnamese", ""),
                    "audio_path": row.get("audio_path", "")
                }
                for row in item.get("data", [])
            ]
        }
        clean_history.append(clean_item)
    
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_history, f, ensure_ascii=False, indent=2)

if 'history' not in st.session_state:
    st.session_state['history'] = load_history_from_disk()

if 'current_view' not in st.session_state:
    st.session_state['current_view'] = None

if 'chat_messages' not in st.session_state:
    st.session_state['chat_messages'] = []

st.title("🎬 Video Transcript & AI Companion")
st.caption("Trích xuất âm thanh, tóm tắt song ngữ & Trợ lý học tập thông minh")

with st.sidebar:
    st.header("⚙️ Cấu hình")
    api_key = st.text_input("Nhập Gemini API Key:", type="password")
    whisper_model_size = st.selectbox("Mô hình Whisper:", ["base", "small", "medium"], index=2)

    st.divider()
    st.header("📚 Lịch sử bài học")
    
    if st.button("➕ Tạo bài mới (Reset)"):
        st.session_state['current_view'] = None
        st.session_state['chat_messages'] = []
        st.rerun()

    st.divider()

    if st.session_state['history']:
        for idx, item in enumerate(st.session_state['history']):
            col_title, col_del = st.columns([4, 1])
            
            with col_title:
                if st.button(f"📖 Bài {idx+1}: {item['title']}", key=f"hist_{idx}"):
                    st.session_state['current_view'] = item
                    st.session_state['chat_messages'] = item.get('chat_history', [])
                    st.rerun()
            
            with col_del:
                if st.button("❌", key=f"del_{idx}"):
                    if st.session_state['current_view'] == item:
                        st.session_state['current_view'] = None
                        st.session_state['chat_messages'] = []
                    
                    if item.get("media_path") and os.path.exists(item["media_path"]):
                        try:
                            os.remove(item["media_path"])
                        except Exception:
                            pass
                    for row in item.get("data", []):
                        if row.get("audio_path") and os.path.exists(row["audio_path"]):
                            try:
                                os.remove(row["audio_path"])
                            except Exception:
                                pass

                    st.session_state['history'].pop(idx)
                    save_history_to_disk(st.session_state['history'])
                    st.rerun()
        
        st.divider()
        if st.button("🗑️ Xóa toàn bộ Lịch sử"):
            st.session_state['history'] = []
            st.session_state['current_view'] = None
            st.session_state['chat_messages'] = []
            if os.path.exists(DB_FILE):
                os.remove(DB_FILE)
            for f in os.listdir(MEDIA_DIR):
                os.remove(os.path.join(MEDIA_DIR, f))
            st.rerun()

if not api_key:
    st.info("Vui lòng nhập Gemini API Key ở thanh bên trái để tiếp tục.")
    st.stop()

@st.cache_resource
def load_whisper_model(model_size):
    return WhisperModel(model_size, device="cpu", compute_type="int8")
  
client = genai.Client(api_key=api_key)

# Màn hình Xem bài từ Lịch sử
if st.session_state['current_view'] is not None:
    view_data = st.session_state['current_view']
    
    col_v1, col_v2 = st.columns([3, 1])
    with col_v1:
        st.info(f"📌 Đang xem bài: **{view_data['title']}**")
    with col_v2:
        # TẠO FILE ZIP ĐỂ CHIA SẺ
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            meta_data = {
                "id": view_data.get("id"),
                "title": view_data.get("title"),
                "file_type": view_data.get("file_type"),
                "summary_en": view_data.get("summary_en"),
                "summary_vi": view_data.get("summary_vi"),
                "chat_history": view_data.get("chat_history", []),
                "media_filename": os.path.basename(view_data.get("media_path", "")),
                "data": [
                    {
                        "speaker": r.get("speaker"),
                        "english": r.get("english"),
                        "vietnamese": r.get("vietnamese"),
                        "audio_filename": os.path.basename(r.get("audio_path", ""))
                    }
                    for r in view_data.get("data", [])
                ]
            }
            zip_file.writestr("lesson.json", json.dumps(meta_data, ensure_ascii=False, indent=2))
            
            m_path = view_data.get("media_path", "")
            if m_path and os.path.exists(m_path):
                zip_file.write(m_path, arcname=os.path.basename(m_path))
            
            for r in view_data.get("data", []):
                a_p = r.get("audio_path", "")
                if a_p and os.path.exists(a_p):
                    zip_file.write(a_p, arcname=os.path.basename(a_p))

        st.download_button(
            label="📦 Export chia sẻ Bài học (.zip)",
            data=zip_buffer.getvalue(),
            file_name=f"{view_data['title']}_package.zip",
            mime="application/zip"
        )

    # Hiển thị lại Media gốc
    media_path = view_data.get("media_path", "")
    if media_path and os.path.exists(media_path):
        if view_data.get("file_type", "").startswith("video"):
            st.video(media_path)
        else:
            st.audio(media_path)

    # Tóm tắt
    st.divider()
    st.subheader("💡 Tóm tắt hội thoại (Song ngữ)")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Tiếng Anh:**")
        st.write(view_data.get("summary_en", ""))
    with c2:
        st.markdown("**Tiếng Việt:**")
        st.write(view_data.get("summary_vi", ""))

    # Bảng thoại
    st.divider()
    st.subheader("📋 Trích xuất thoại & Băng âm thanh thực")
    for item in view_data.get('data', []):
        col1, col2, col3, col4 = st.columns([1.5, 4, 4, 3])
        with col1:
            st.write(f"**{item.get('speaker', 'Thoại')}**")
        with col2:
            st.write(item.get("english", ""))
        with col3:
            st.write(item.get("vietnamese", ""))
        with col4:
            aud_p = item.get("audio_path", "")
            if aud_p and os.path.exists(aud_p):
                st.audio(aud_p, format="audio/wav")
            else:
                st.caption("Không tìm thấy âm thanh")

    # AI Companion
    st.divider()
    st.subheader("🤖 AI Companion (Trợ lý hỏi đáp)")
    for msg in st.session_state['chat_messages']:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input("Hỏi AI về từ vựng, ngữ pháp hoặc ngữ cảnh bài học này...")
    if user_input:
        st.session_state['chat_messages'].append({"role": "user", "content": user_input})
        
        context = f"Nội dung hội thoại:\n{json.dumps([{k:v for k,v in r.items() if k!='audio_path'} for r in view_data['data']], ensure_ascii=False)}"
        prompt_chat = f"{context}\n\nNgười dùng hỏi: {user_input}\n\nHãy trả lời chi tiết, dễ hiểu:"
        
        res = client.models.generate_content(model='gemini-3.5-flash', contents=[prompt_chat])
        st.session_state['chat_messages'].append({"role": "assistant", "content": res.text})
        
        view_data['chat_history'] = st.session_state['chat_messages']
        save_history_to_disk(st.session_state['history'])
        st.rerun()

    st.stop()

# Màn hình chính: Tải file mới HOẶC Nhập gói bài học
st.subheader("📥 Nhập bài học được chia sẻ (.zip)")
shared_zip = st.file_uploader("Tải lên file gói bài học (.zip) được chia sẻ:", type=["zip"], key="zip_import")

if shared_zip:
    if st.button("📥 Nạp bài học này vào Lịch sử"):
        with zipfile.ZipFile(shared_zip, "r") as zf:
            if "lesson.json" in zf.namelist():
                meta_bytes = zf.read("lesson.json")
                meta = json.loads(meta_bytes.decode("utf-8"))
                
                for file_info in zf.infolist():
                    if file_info.filename != "lesson.json":
                        target_p = os.path.join(MEDIA_DIR, os.path.basename(file_info.filename))
                        with open(target_p, "wb") as f_out:
                            f_out.write(zf.read(file_info.filename))

                new_media_p = os.path.join(MEDIA_DIR, meta.get("media_filename", ""))
                new_data = []
                for r in meta.get("data", []):
                    new_data.append({
                        "speaker": r.get("speaker"),
                        "english": r.get("english"),
                        "vietnamese": r.get("vietnamese"),
                        "audio_path": os.path.join(MEDIA_DIR, r.get("audio_filename", ""))
                    })

                imported_item = {
                    "id": meta.get("id"),
                    "title": meta.get("title"),
                    "file_type": meta.get("file_type"),
                    "media_path": new_media_p,
                    "summary_en": meta.get("summary_en"),
                    "summary_vi": meta.get("summary_vi"),
                    "data": new_data,
                    "chat_history": meta.get("chat_history", [])
                }

                st.session_state['history'].append(imported_item)
                st.session_state['current_view'] = imported_item
                save_history_to_disk(st.session_state['history'])
                st.success("Đã nạp bài học thành công!")
                st.rerun()

st.divider()
st.subheader("📤 Hoặc Xử lý bài mới từ Video/Audio gốc")
uploaded_file = st.file_uploader(
    "Tải lên file Video hoặc Audio (MP4, MP3, WAV, MOV):", 
    type=["mp4", "mp3", "wav", "mov"],
    key="media_upload"
)

if uploaded_file:
    file_bytes = uploaded_file.getvalue()
    if uploaded_file.type.startswith("video"):
        st.video(file_bytes)
    else:
        st.audio(file_bytes)

    if st.button("🚀 Bắt đầu trích xuất, Tóm tắt & Dịch"):
        import time
        item_id = str(int(time.time()))
        
        media_ext = os.path.splitext(uploaded_file.name)[1]
        saved_media_path = os.path.join(MEDIA_DIR, f"{item_id}_orig{media_ext}")
        with open(saved_media_path, "wb") as f:
            f.write(file_bytes)

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, f"input_media{media_ext}")
            wav_path = os.path.join(temp_dir, "extracted_sound.wav")

            with open(input_path, "wb") as f:
                f.write(file_bytes)

            with st.spinner("1/4. Đang tách âm thanh gốc..."):
                if uploaded_file.type.startswith("video"):
                    video = VideoFileClip(input_path)
                    video.audio.write_audiofile(wav_path, logger=None)
                    video.close()
                else:
                    audio = AudioFileClip(input_path)
                    audio.write_audiofile(wav_path, logger=None)
                    audio.close()

            with st.spinner(f"2/4. Whisper ({whisper_model_size}) đang phân tích mốc thời gian..."):
                model = load_whisper_model(whisper_model_size)
                   segments, info = model.transcribe(
                wav_path,
                language="en",
                word_timestamps=True,
                no_speech_threshold=0.6,
                temperature=0.0
            )
                       raw_segments = [
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "words": [{"start": w.start, "end": w.end, "word": w.word} for w in seg.words] if seg.words else []
                }
                        for seg in segments:
                        ]

            with st.spinner("3/4. Gemini đang gộp lượt nói, tóm tắt & dịch thuật..."):
                transcript_text = "\n".join([f"[{s['id']}] ({s['start']:.2f}s - {s['end']:.2f}s): {s['text'].strip()}" for s in raw_segments])
                
                prompt = f"""
                Dưới me là danh sách các câu thoại kèm mốc thời gian:
                {transcript_text}

                Nhiệm vụ:
                1. Gộp các câu thoại liên tiếp của CÙNG MỘT NGƯỜI NÓI (Check-in Agent / Passenger) thành 1 lượt nói.
                2. Tóm tắt nội dung chính bài hội thoại bằng cả tiếng Anh và tiếng Việt.

                Trả về duy nhất JSON dạng:
                {{
                  "summary_en": "Tóm tắt ngắn gọn bài hội thoại bằng tiếng Anh",
                  "summary_vi": "Tóm tắt ngắn gọn bài hội thoại bằng tiếng Việt",
                  "grouped_data": [
                    {{
                      "speaker": "Check-in Agent",
                      "start_id": 0,
                      "end_id": 2,
                      "english": "Văn bản tiếng Anh lượt nói",
                      "vietnamese": "Dịch tiếng Việt lượt nói"
                    }}
                  ]
                }}
                """

                response = client.models.generate_content(
                    model='gemini-3.5-flash',
                    contents=[prompt]
                )

                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                
                res_json = json.loads(raw_text.strip())

            with st.spinner("4/4. Cắt & lưu âm thanh từng đoạn..."):
                full_audio = AudioSegment.from_wav(wav_path)
                total_duration_ms = len(full_audio)
                seg_map = {s["id"]: s for s in raw_segments}
                final_data = []

                for idx, group in enumerate(res_json.get("grouped_data", [])):
                    s_id = group.get("start_id")
                    e_id = group.get("end_id")

                    audio_save_path = ""
                    if s_id in seg_map and e_id in seg_map:
                        start_ms = max(0, int(seg_map[s_id]["start"] * 1000) - 20)
                        end_ms = min(total_duration_ms, int(seg_map[e_id]["end"] * 1000) + 20)

                        chunk = full_audio[start_ms:end_ms]
                        audio_save_path = os.path.join(MEDIA_DIR, f"{item_id}_chunk_{idx}.wav")
                        chunk.export(audio_save_path, format="wav")

                    final_data.append({
                        "speaker": group.get("speaker", "Speaker"),
                        "english": group.get("english", ""),
                        "vietnamese": group.get("vietnamese", ""),
                        "audio_path": audio_save_path
                    })

            new_item = {
                "id": item_id,
                "title": uploaded_file.name,
                "file_type": uploaded_file.type,
                "media_path": saved_media_path,
                "summary_en": res_json.get("summary_en", ""),
                "summary_vi": res_json.get("summary_vi", ""),
                "data": final_data,
                "chat_history": []
            }
            st.session_state['history'].append(new_item)
            st.session_state['current_view'] = new_item
            
            save_history_to_disk(st.session_state['history'])
            st.rerun()
