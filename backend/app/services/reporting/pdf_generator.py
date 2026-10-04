import html
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.models import Case, Explanation, ModelVersion, Prediction
from app.services.fusion.fusion_service import fuse

NAVY = colors.HexColor("#243746")
ACCENT = colors.HexColor("#2F6F78")
MUTED = colors.HexColor("#64727A")
LINE = colors.HexColor("#D8E0E3")
PALE = colors.HexColor("#F3F6F7")
TEXT = colors.HexColor("#1D2A30")


class NumberedCanvas(canvas.Canvas):
    """Canvas that adds Page X of Y after the document has been laid out."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(page_count)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_count: int) -> None:
        self.saveState()
        width, _ = letter
        report_id = getattr(self, "report_id", "Not available")
        self.setStrokeColor(LINE)
        self.line(0.7 * inch, 0.58 * inch, width - 0.7 * inch, 0.58 * inch)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(MUTED)
        self.drawString(0.7 * inch, 0.38 * inch, "MediScanX | AI-assisted screening / decision-support prototype")
        self.drawRightString(width - 0.7 * inch, 0.38 * inch, f"Report ID: {report_id} | Page {self._pageNumber} of {page_count}")
        self.restoreState()


def _header_footer(canvas_obj: canvas.Canvas, doc: SimpleDocTemplate) -> None:
    canvas_obj.report_id = getattr(doc, "report_id", "Not available")
    canvas_obj.saveState()
    width, height = letter
    canvas_obj.setFillColor(NAVY)
    canvas_obj.setFont("Helvetica-Bold", 9)
    canvas_obj.drawString(0.7 * inch, height - 0.45 * inch, "MediScanX")
    canvas_obj.setFillColor(MUTED)
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.drawRightString(width - 0.7 * inch, height - 0.45 * inch, "Multimodal Cardiothoracic AI Screening Report")
    canvas_obj.setStrokeColor(LINE)
    canvas_obj.line(0.7 * inch, height - 0.58 * inch, width - 0.7 * inch, height - 0.58 * inch)
    canvas_obj.restoreState()


def _safe(value: Any) -> str:
    return html.escape(str(value)) if value is not None else "Not available"


def _fmt_percent(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "Not available"


def _fmt_score(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "Not available"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    return {
        "title": ParagraphStyle("ReportTitle", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=4),
        "subtitle": ParagraphStyle("ReportSubtitle", parent=base, fontSize=9, leading=12, textColor=MUTED, spaceAfter=16),
        "section": ParagraphStyle("Section", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=4, spaceAfter=7, keepWithNext=True),
        "subsection": ParagraphStyle("Subsection", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=ACCENT, spaceBefore=6, spaceAfter=5, keepWithNext=True),
        "body": ParagraphStyle("Body", parent=base, fontSize=8.7, leading=12, textColor=TEXT, spaceAfter=6),
        "small": ParagraphStyle("Small", parent=base, fontSize=7.7, leading=10, textColor=MUTED, spaceAfter=4),
        "caption": ParagraphStyle("Caption", parent=base, fontSize=7.5, leading=9, textColor=MUTED, alignment=1, spaceBefore=4, spaceAfter=6),
        "disclaimer": ParagraphStyle("Disclaimer", parent=base, fontSize=8, leading=11, textColor=TEXT, backColor=PALE, borderColor=LINE, borderWidth=0.5, borderPadding=7, spaceBefore=5, spaceAfter=7),
        "center": ParagraphStyle("Center", parent=base, fontSize=8, leading=10, alignment=1, textColor=MUTED),
    }


def _table(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands: list[tuple[Any, ...]] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), PALE),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ])
    table.setStyle(TableStyle(commands))
    return table


def _image_size(path: str, max_width: float, max_height: float) -> tuple[float, float]:
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as image:
            width, height = image.size
        scale = min(max_width / width, max_height / height)
        return width * scale, height * scale
    except Exception:
        return max_width, max_height


def _asset(src: str | None, destination: Path, suffix: str) -> str | None:
    if not src or not Path(src).exists():
        return None
    target = destination / f"{suffix}_{Path(src).name}"
    shutil.copy2(src, target)
    return str(target)


def _fusion_data(db: Session, img_preds: list[Prediction], ecg_preds: list[Prediction], fusion_pred: Prediction | None) -> Any:
    img_probs = {item.label: item.probability for item in img_preds} or None
    ecg_probs = {item.label: item.probability for item in ecg_preds} or None
    if not img_probs and not ecg_probs:
        return None
    image_model = db.query(ModelVersion).filter(ModelVersion.name == "CheXNet-DenseNet121").first()
    ecg_model = db.query(ModelVersion).filter(ModelVersion.name == "PTB-XL-1D-CNN").first()
    image_weight = image_model.val_auroc if image_model and image_model.val_auroc is not None else None
    ecg_weight = ecg_model.val_auroc if ecg_model and ecg_model.val_auroc is not None else None
    try:
        return fuse(img_probs, ecg_probs, image_weight, ecg_weight)
    except Exception:
        if fusion_pred is None:
            return None
        return type("FallbackFusion", (), {
            "image_score": None,
            "ecg_score": None,
            "fusion_score": fusion_pred.probability,
            "risk_band": fusion_pred.label.replace("cardiac_risk:", ""),
            "disagreement": False,
            "difference": None,
            "weight_image": image_weight,
            "weight_ecg": ecg_weight,
            "modality_used": "both" if img_preds and ecg_preds else ("image_only" if img_preds else "ecg_only"),
        })()


def _heart_rate(case: Case) -> str:
    try:
        from app.services.ecg.ecg_service import estimate_heart_rate
        from app.services.preprocessing.ecg import load_ecg_csv, load_ecg_wfdb, preprocess_ecg
        record = case.ecg_records[0]
        signal_path = Path(record.file_path)
        sampling_rate = record.sampling_rate or 100.0
        if signal_path.suffix.lower() == ".csv":
            signal, assumed_rate = load_ecg_csv(signal_path.read_bytes())
        else:
            signal, assumed_rate = load_ecg_wfdb(str(signal_path.with_suffix("")))
        sampling_rate = record.sampling_rate or assumed_rate
        processed, _ = preprocess_ecg(signal, fs=sampling_rate)
        rate = estimate_heart_rate(processed[1], fs=sampling_rate) or estimate_heart_rate(processed[0], fs=sampling_rate)
        return f"{rate:.1f} bpm" if rate is not None else "Not available"
    except Exception:
        return "Not available"


def _ecg_plot(case: Case, destination: Path) -> str | None:
    try:
        from app.services.ecg.ecg_service import render_ecg_plot
        from app.services.preprocessing.ecg import load_ecg_csv, load_ecg_wfdb, preprocess_ecg

        record = case.ecg_records[0]
        signal_path = Path(record.file_path)
        if signal_path.suffix.lower() == ".csv":
            signal, assumed_rate = load_ecg_csv(signal_path.read_bytes())
        else:
            signal, assumed_rate = load_ecg_wfdb(str(signal_path.with_suffix("")))
        sampling_rate = record.sampling_rate or assumed_rate
        processed, _ = preprocess_ecg(signal, fs=sampling_rate)
        target = destination / f"{case.id}_ecg_waveform.png"
        render_ecg_plot(processed, fs=sampling_rate, save_path=str(target))
        return str(target) if target.exists() else None
    except Exception:
        return None


def generate_pdf_report(case: Case, db: Session, save_dir: str = "uploads/reports", report_id: str | None = None) -> str:
    """Generate a structured report from persisted model outputs and assets."""
    styles = _styles()
    output_dir = Path(save_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = report_id or f"RPT-{str(case.id).split('-')[0].upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    filename = f"MediScanX_{case.patient.anon_code}_{str(case.id).split('-')[0].upper()}_{datetime.utcnow().strftime('%Y-%m-%d_%H%M%S')}.pdf"
    file_path = output_dir / filename
    predictions = db.query(Prediction).filter(Prediction.case_id == case.id).all()
    img_preds = [item for item in predictions if item.source == "image"]
    ecg_preds = [item for item in predictions if item.source == "ecg"]
    fusion_pred = next((item for item in predictions if item.source == "fusion"), None)
    explanations = db.query(Explanation).join(Prediction).filter(Prediction.case_id == case.id).all()
    fusion = _fusion_data(db, img_preds, ecg_preds, fusion_pred)
    has_image, has_ecg = bool(img_preds), bool(ecg_preds)
    modality = " + ".join(filter(None, ["Chest X-ray" if has_image else "", "12-lead ECG" if has_ecg else ""])) or "Not available"
    report_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    dates = [item.uploaded_at for item in [*case.imaging_studies, *case.ecg_records] if item.uploaded_at]
    examination_date = min(dates).strftime("%Y-%m-%d %H:%M UTC") if dates else "Not available"

    doc = SimpleDocTemplate(str(file_path), pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.78 * inch, bottomMargin=0.78 * inch, title="MediScanX Multimodal Cardiothoracic AI Screening Report")
    doc.report_id = report_id
    story: list[Any] = []

    story += [Paragraph("Multimodal Cardiothoracic AI Screening Report", styles["title"]), Paragraph("AI-assisted screening / decision-support prototype", styles["subtitle"]), Paragraph("1. Case information", styles["section"])]
    info = [
        [Paragraph("Patient code", styles["small"]), Paragraph(_safe(case.patient.anon_code), styles["body"]), Paragraph("Case ID", styles["small"]), Paragraph(_safe(case.id), styles["body"])],
        [Paragraph("Age", styles["small"]), Paragraph(_safe(case.patient.age), styles["body"]), Paragraph("Sex", styles["small"]), Paragraph(_safe(case.patient.sex), styles["body"])],
        [Paragraph("Examination date", styles["small"]), Paragraph(examination_date, styles["body"]), Paragraph("Report date", styles["small"]), Paragraph(report_date, styles["body"])],
        [Paragraph("Report status", styles["small"]), Paragraph("Completed", styles["body"]), Paragraph("Available modalities", styles["small"]), Paragraph(_safe(modality), styles["body"])],
    ]
    story += [_table(info, [1.15 * inch, 2.15 * inch, 1.25 * inch, 2.35 * inch], False), Spacer(1, 0.12 * inch), Paragraph("2. Executive screening summary", styles["section"])]
    summary = [[Paragraph("Measure", styles["small"]), Paragraph("Backend value", styles["small"])]]
    for label, value in [("Imaging screening score", _fmt_score(getattr(fusion, "image_score", None))), ("ECG screening score", _fmt_score(getattr(fusion, "ecg_score", None))), ("Fusion score", _fmt_score(getattr(fusion, "fusion_score", None))), ("Risk band", _safe(getattr(fusion, "risk_band", None))), ("Modality disagreement", "Yes" if getattr(fusion, "disagreement", None) else "No"), ("Modality used", _safe(getattr(fusion, "modality_used", modality)))]:
        summary.append([Paragraph(label, styles["body"]), Paragraph(value, styles["body"])])
    story += [_table(summary, [3.2 * inch, 3.7 * inch]), Paragraph("What this result means", styles["subsection"]), Paragraph("MediScanX analyzed the available chest X-ray and/or ECG using its configured AI screening pipeline. The reported score is a model-derived screening indicator, not a diagnosis. Individual model findings are shown separately from the overall cardiothoracic screening score.", styles["body"]), Paragraph("Important limitation: This report presents AI model outputs for academic screening and decision-support purposes. It does not establish the presence or absence of disease and should not replace professional clinical assessment.", styles["disclaimer"])]

    if has_image:
        story += [PageBreak(), Paragraph("3. Chest X-ray AI analysis", styles["section"]), Paragraph("Source image", styles["subsection"])]
        original = _asset(case.imaging_studies[0].file_path if case.imaging_studies else None, output_dir, f"{case.id}_original")
        if original:
            width, height = _image_size(original, 6.4 * inch, 3.15 * inch)
            story += [Image(original, width=width, height=height), Paragraph("Original chest X-ray submitted for AI analysis.", styles["caption"])]
        else:
            story.append(Paragraph("Original chest X-ray not available.", styles["small"]))
        study = case.imaging_studies[0] if case.imaging_studies else None
        image_format = Path(study.original_filename or study.file_path if study else "").suffix.upper().lstrip(".") or "Not available"
        story += [Paragraph("Image quality / validation", styles["subsection"]), _table([[Paragraph("Validation", styles["small"]), Paragraph("Passed", styles["body"])], [Paragraph("Image format", styles["small"]), Paragraph(image_format, styles["body"])], [Paragraph("Quality flag", styles["small"]), Paragraph(_safe(study.quality_flag if study else None), styles["body"])]], [1.8 * inch, 5.1 * inch], False), Paragraph("Model findings", styles["subsection"])]
        rows = [[Paragraph("Finding", styles["small"]), Paragraph("Model probability", styles["small"]), Paragraph("Threshold / status", styles["small"])]]
        for item in sorted(img_preds, key=lambda value: value.probability, reverse=True):
            rows.append([Paragraph(_safe(item.label), styles["body"]), Paragraph(_fmt_percent(item.probability), styles["body"]), Paragraph("Configured / above" if item.above_threshold else "Configured / below", styles["body"])])
        story.append(_table(rows, [2.6 * inch, 1.7 * inch, 2.6 * inch]))
        top = sorted(img_preds, key=lambda value: value.probability, reverse=True)[:5]
        highest = top[0] if top else None
        others = ", ".join(_safe(item.label) for item in top[1:3]) or "no other outputs"
        story += [Paragraph("Top model outputs", styles["subsection"]), Paragraph("These are the highest model probabilities and should not be interpreted as confirmed clinical findings.", styles["small"]), Paragraph("<br/>".join(f"{index}. {_safe(item.label)} — {_fmt_percent(item.probability)}" for index, item in enumerate(top, 1)), styles["body"]), Paragraph("Understanding the X-ray model result", styles["subsection"]), Paragraph(f"What the model output was: The highest model output in this analysis was {_safe(highest.label) if highest else 'not available'} at {_fmt_percent(highest.probability) if highest else 'not available'}.<br/><br/>What that means: The imaging model assigned this probability score under its learned classification framework. It does not mean that the output is clinically confirmed.<br/><br/>How it relates to the screening score: The overall imaging screening score is calculated separately from the configured cardiothoracic inputs, so a higher probability for another X-ray finding does not necessarily increase that score. Other relatively higher model outputs included {others}.", styles["body"])]
        if fusion:
            cardio = {item.label: item.probability for item in img_preds}
            score_rows = [[Paragraph("Input", styles["small"]), Paragraph("Probability", styles["small"])]] + [[Paragraph(label, styles["body"]), Paragraph(_fmt_percent(cardio.get(label)), styles["body"])] for label in ("Cardiomegaly", "Edema", "Effusion")] + [[Paragraph("Image screening score", styles["body"]), Paragraph(_fmt_score(getattr(fusion, "image_score", None)), styles["body"])]]
            story += [Paragraph("Cardiothoracic screening score", styles["subsection"]), _table(score_rows, [3.8 * inch, 2.2 * inch]), Paragraph("Configured calculation: p_img = max(Cardiomegaly, Edema, Effusion). This score is a configured screening indicator derived from those specified model outputs. It is separate from the other individual X-ray model probabilities.", styles["body"]), PageBreak(), Paragraph("4. X-ray explainability", styles["section"])]
        gradcam = next((item for item in explanations if item.type == "gradcam"), None)
        saved_gradcam = _asset(gradcam.file_path if gradcam else None, output_dir, f"{case.id}_gradcam")
        visual = []
        for path, label in ((original, "Original X-ray"), (saved_gradcam, "Grad-CAM explanation")):
            if path:
                width, height = _image_size(path, 3.1 * inch, 3.1 * inch)
                visual.append(Image(path, width=width, height=height))
            else:
                visual.append(Paragraph(f"{label} not available.", styles["center"]))
        story += [_table([visual, [Paragraph("Original X-ray", styles["caption"]), Paragraph("Grad-CAM explanation", styles["caption"])]], [3.35 * inch, 3.35 * inch], False), Paragraph(f"Explainability target: {_safe(gradcam.prediction.label if gradcam and gradcam.prediction else None)}", styles["small"]), Paragraph("The Grad-CAM visualization highlights image regions that contributed to the selected model output. Brighter or highlighted regions indicate greater contribution to the model's activation for the selected target. This visualization describes model attention; it does not prove that a highlighted region represents disease, establish causality, or provide definitive anatomical localization.", styles["body"])]
        model = img_preds[0].model_version if img_preds else None
        story += [Paragraph("Model traceability", styles["subsection"]), _table([[Paragraph("Model", styles["small"]), Paragraph(_safe(model.name if model else None), styles["body"])], [Paragraph("Model version", styles["small"]), Paragraph(_safe(model.version if model else None), styles["body"])], [Paragraph("Inference time", styles["small"]), Paragraph(_safe(f"{img_preds[0].inference_ms:.1f} ms" if img_preds and img_preds[0].inference_ms is not None else None), styles["body"])], [Paragraph("Preprocessing", styles["small"]), Paragraph("Configured image preprocessing; detailed trace not persisted.", styles["body"])]], [1.8 * inch, 4.9 * inch], False)]

    if has_ecg:
        story += [PageBreak(), Paragraph("5. ECG AI analysis", styles["section"]), Paragraph("ECG model output", styles["subsection"])]
        rows = [[Paragraph("Finding", styles["small"]), Paragraph("Probability", styles["small"]), Paragraph("Threshold / status", styles["small"])]]
        for item in sorted(ecg_preds, key=lambda value: value.probability, reverse=True):
            rows.append([Paragraph(_safe(item.label), styles["body"]), Paragraph(_fmt_percent(item.probability), styles["body"]), Paragraph("Configured / above" if item.above_threshold else "Configured / below", styles["body"])])
        story += [_table(rows, [2.0 * inch, 1.7 * inch, 3.2 * inch]), Paragraph(f"Heart rate: {_heart_rate(case)}", styles["body"])]
        model = ecg_preds[0].model_version if ecg_preds else None
        story += [Paragraph(f"Model: {_safe(model.name if model else None)} | Version: {_safe(model.version if model else None)} | Inference time: {_safe(f'{ecg_preds[0].inference_ms:.1f} ms' if ecg_preds and ecg_preds[0].inference_ms is not None else None)}", styles["small"])]
        highest = max(ecg_preds, key=lambda value: value.probability) if ecg_preds else None
        story += [Paragraph("ECG model interpretation", styles["subsection"]), Paragraph(f"The ECG model produced its highest output for {_safe(highest.label) if highest else 'not available'} at {_fmt_percent(highest.probability) if highest else 'not available'}. This represents a model output and does not constitute a clinical interpretation or diagnosis.", styles["body"]), Paragraph("ECG explainability", styles["subsection"])]
        waveform = _ecg_plot(case, output_dir)
        if waveform:
            width, height = _image_size(waveform, 6.4 * inch, 3.1 * inch)
            story += [Image(waveform, width=width, height=height), Paragraph("Original 12-lead ECG waveform rendered from the submitted signal.", styles["caption"])]
        else:
            story.append(Paragraph("Original 12-lead ECG waveform not available.", styles["small"]))
        saliency = next((item for item in explanations if item.type == "saliency"), None)
        saved_saliency = _asset(saliency.file_path if saliency else None, output_dir, f"{case.id}_saliency")
        if saved_saliency:
            width, height = _image_size(saved_saliency, 6.4 * inch, 3.2 * inch)
            story += [Image(saved_saliency, width=width, height=height), Paragraph("ECG saliency visualization generated by the backend.", styles["caption"])]
        else:
            story.append(Paragraph("ECG saliency visualization not available.", styles["small"]))

    story += [PageBreak(), Paragraph("6. Multimodal fusion", styles["section"])]
    if fusion:
        rows = [[Paragraph("Measure", styles["small"]), Paragraph("Value", styles["small"])]]
        for label, value in [("X-ray screening score", _fmt_score(getattr(fusion, "image_score", None))), ("ECG screening score", _fmt_score(getattr(fusion, "ecg_score", None))), ("Image weight", _safe(getattr(fusion, "weight_image", None))), ("ECG weight", _safe(getattr(fusion, "weight_ecg", None))), ("Fusion score", _fmt_score(getattr(fusion, "fusion_score", None))), ("Risk band", _safe(getattr(fusion, "risk_band", None))), ("Difference", _fmt_score(getattr(fusion, "difference", None))), ("Disagreement", "Yes" if getattr(fusion, "disagreement", None) else "No"), ("Modality used", _safe(getattr(fusion, "modality_used", None)))]:
            rows.append([Paragraph(label, styles["body"]), Paragraph(value, styles["body"])])
        story.append(_table(rows, [3.2 * inch, 3.1 * inch]))
        modality_note = "This case was analyzed using both X-ray and ECG outputs." if getattr(fusion, "modality_used", "") == "both" else f"This case was analyzed using {_safe(getattr(fusion, 'modality_used', 'one modality')).replace('_', ' ')}. No multimodal fusion between X-ray and ECG was performed."
        disagreement_note = "Substantial modality disagreement was identified according to the configured criterion." if getattr(fusion, "disagreement", False) else "No substantial modality disagreement was identified according to the configured criterion."
        story += [Paragraph("How the fusion result was obtained", styles["subsection"]), Paragraph(f"{modality_note} The multimodal score combines the available modality-specific screening scores using the configured MediScanX fusion methodology. {disagreement_note}", styles["body"])]

    highest_img = max(img_preds, key=lambda value: value.probability) if img_preds else None
    highest_ecg = max(ecg_preds, key=lambda value: value.probability) if ecg_preds else None
    story += [Paragraph("7. Final AI screening summary", styles["section"]), Paragraph(f"Available analysis: {_safe(modality)}.<br/><br/>The imaging model's highest output was {_safe(highest_img.label) if highest_img else 'not available'} at {_fmt_percent(highest_img.probability) if highest_img else 'not available'}.<br/>The ECG model's highest output was {_safe(highest_ecg.label) if highest_ecg else 'not available'} at {_fmt_percent(highest_ecg.probability) if highest_ecg else 'not available'}.<br/>The resulting configured screening score was {_fmt_score(getattr(fusion, 'fusion_score', None))}, corresponding to the {_safe(getattr(fusion, 'risk_band', None))} screening band.<br/><br/>These outputs represent AI model screening indicators and should not be interpreted as confirmed clinical findings.", styles["body"]), Paragraph("This report does not establish the presence or absence of disease. Clinical review remains necessary, and model attention visualizations should not be treated as radiologist annotations or proof of causality.", styles["disclaimer"])]
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer, canvasmaker=NumberedCanvas)
    return str(file_path)
