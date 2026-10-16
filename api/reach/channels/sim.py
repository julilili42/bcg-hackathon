"""Virtual demo phone endpoints: the same voice and SMS handlers, without the Twilio signature.

The web map's Nokia-style phone posts here so a demo works while the real number has signature
validation on. Enabled by DEMO_PHONE (default on); set DEMO_PHONE=0 in production.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from reach.channels.twilio import sms_impl, voice_answer_impl, voice_handle_impl, voice_start_impl

router = APIRouter(prefix="/api/sim", tags=["web"])
SIM_BASE = "/api/sim/voice"


async def sim_form(request: Request) -> dict[str, str]:
    if not request.app.state.settings.demo_phone:
        raise HTTPException(status_code=404, detail="demo phone disabled (DEMO_PHONE=0)")
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    params.setdefault("From", "+15005550006")  # Twilio magic test number, never a real person
    return params


SimForm = Annotated[dict[str, str], Depends(sim_form)]


@router.post("/voice")
def sim_voice_start(request: Request, form: SimForm, lang: str = Query(default="sw")) -> Response:
    return voice_start_impl(request, form, base=SIM_BASE, lang=lang)


@router.post("/voice/handle")
def sim_voice_handle(
    request: Request,
    form: SimForm,
    lang: str = Query(default="sw"),
    domain: str = Query(default=""),
    retry: int = Query(default=0),
) -> Response:
    return voice_handle_impl(request, form, lang, domain, retry, base=SIM_BASE, limit=False)


@router.post("/voice/answer")
def sim_voice_answer(
    request: Request,
    form: SimForm,
    lang: str = Query(default="sw"),
    domain: str = Query(default=""),
    retry: int = Query(default=0),
) -> Response:
    return voice_answer_impl(request, form, lang, domain, retry, base=SIM_BASE)


@router.post("/sms")
def sim_sms(request: Request, form: SimForm) -> Response:
    return sms_impl(request, form, limit=False)
