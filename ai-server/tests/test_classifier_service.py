"""
Species classifier service.

The classifier is currently bypassed in production — the detector is binary and the
angler confirms the species — but the service is loaded at startup, reported by the
health endpoints, and its output columns are persisted. It had no test coverage at
all.

What matters here is the preprocessing. It must match what the model was trained
on: letterbox (aspect-preserving) resize to 224, ImageNet normalisation, and
channel-first layout. A mismatch does not raise; it produces confident nonsense.
And when no model is present the service must degrade to "unavailable, ask the
user" rather than fail the request.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.services.classifier_service import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    INPUT_SIZE,
    ClassifierService,
    get_loaded_classifier_service,
)


def bare_service() -> ClassifierService:
    """
    Build a service without running the model-loading constructor.

    The preprocessing helpers are pure, so they can be exercised without a
    checkpoint on disk.
    """
    service = ClassifierService.__new__(ClassifierService)
    service.session = None
    service.labels = {}
    service._available = False
    return service


def bgr_image(width: int, height: int, value: int = 120) -> np.ndarray:
    """Build a uniform BGR image."""
    return np.full((height, width, 3), value, dtype=np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# Letterbox resize
# ─────────────────────────────────────────────────────────────────────────────
def test_letterbox_output_is_square_at_the_model_input_size() -> None:
    service = bare_service()

    result = service._letterbox_rgb(bgr_image(640, 200))

    assert result.shape[:2] == (INPUT_SIZE, INPUT_SIZE)


@pytest.mark.parametrize(
    ("width", "height"),
    [(640, 200), (200, 640), (300, 300), (1920, 1080), (37, 211)],
)
def test_letterbox_is_square_for_any_input_shape(width: int, height: int) -> None:
    service = bare_service()

    result = service._letterbox_rgb(bgr_image(width, height))

    assert result.shape[:2] == (INPUT_SIZE, INPUT_SIZE)


def test_letterbox_preserves_aspect_ratio_by_padding() -> None:
    """
    Squashing a wide fish into a square would distort its proportions, and the
    model was trained on letterboxed inputs.
    """
    service = bare_service()
    # A wide bright image on a distinguishable background.
    image = bgr_image(400, 100, value=255)

    result = service._letterbox_rgb(image)

    # The content band is 100/400 of the width => 56 rows of 224, centred.
    content_rows = np.where((result == 255).all(axis=2).any(axis=1))[0]
    assert len(content_rows) == pytest.approx(56, abs=2)
    # Centred: roughly equal padding above and below.
    assert content_rows[0] == pytest.approx(INPUT_SIZE - content_rows[-1] - 1, abs=2)


def test_letterbox_pads_with_the_neutral_grey() -> None:
    """
    114 is the value the training pipeline used. A different pad colour shifts the
    input distribution the model sees at the borders.
    """
    service = bare_service()

    result = service._letterbox_rgb(bgr_image(400, 100, value=255))

    assert tuple(result[0, 0]) == (114, 114, 114)


def test_letterbox_of_a_square_image_needs_no_padding() -> None:
    service = bare_service()

    result = service._letterbox_rgb(bgr_image(300, 300, value=200))

    assert (result == 200).all()


def test_letterbox_upscales_a_small_image_to_the_input_size() -> None:
    """Unlike frame extraction, the model input size is fixed and must be filled."""
    service = bare_service()

    result = service._letterbox_rgb(bgr_image(32, 32))

    assert result.shape[:2] == (INPUT_SIZE, INPUT_SIZE)


# ─────────────────────────────────────────────────────────────────────────────
# Preprocessing
# ─────────────────────────────────────────────────────────────────────────────
def test_preprocess_produces_a_nchw_batch() -> None:
    service = bare_service()

    blob = service._preprocess(bgr_image(320, 240))

    assert blob.shape == (1, 3, INPUT_SIZE, INPUT_SIZE)


def test_preprocess_returns_float32() -> None:
    """ONNX Runtime rejects a float64 input for a float32 graph."""
    service = bare_service()

    assert service._preprocess(bgr_image(320, 240)).dtype == np.float32


def test_preprocess_applies_imagenet_normalisation() -> None:
    """
    A mid-grey pixel must land where ImageNet statistics put it. Wrong statistics
    do not raise — they just move every prediction.
    """
    service = bare_service()

    blob = service._preprocess(bgr_image(224, 224, value=128))

    expected = (128 / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    # Channel order is RGB after conversion; compare the centre pixel.
    centre = blob[0, :, INPUT_SIZE // 2, INPUT_SIZE // 2]
    np.testing.assert_allclose(centre, expected, rtol=1e-4, atol=1e-4)


def test_preprocess_converts_bgr_to_rgb() -> None:
    """
    OpenCV decodes BGR; the model expects RGB. Getting this wrong swaps red and
    blue, which for a fish is exactly the colour information that distinguishes
    species.
    """
    service = bare_service()
    # Pure blue in BGR.
    image = np.zeros((224, 224, 3), dtype=np.uint8)
    image[:, :, 0] = 255

    blob = service._preprocess(image)
    centre = blob[0, :, INPUT_SIZE // 2, INPUT_SIZE // 2]

    # After BGR->RGB the saturated channel must be the last one, not the first.
    assert centre[2] > centre[0]


def test_preprocess_is_deterministic() -> None:
    service = bare_service()
    image = bgr_image(320, 240)

    np.testing.assert_array_equal(service._preprocess(image), service._preprocess(image))


# ─────────────────────────────────────────────────────────────────────────────
# Softmax
# ─────────────────────────────────────────────────────────────────────────────
def test_softmax_sums_to_one() -> None:
    service = bare_service()

    probs = service._softmax(np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32))

    assert probs.sum() == pytest.approx(1.0)


def test_softmax_preserves_ranking() -> None:
    service = bare_service()

    probs = service._softmax(np.array([0.1, 5.0, 2.0], dtype=np.float32))

    assert int(np.argmax(probs)) == 1


def test_softmax_is_numerically_stable_for_large_logits() -> None:
    """
    The max is subtracted before exponentiating. Without that, exp(1000) overflows
    to inf and every probability becomes nan.
    """
    service = bare_service()

    probs = service._softmax(np.array([1000.0, 1001.0, 999.0], dtype=np.float32))

    assert np.isfinite(probs).all()
    assert probs.sum() == pytest.approx(1.0)


def test_softmax_of_equal_logits_is_uniform() -> None:
    service = bare_service()

    probs = service._softmax(np.zeros(4, dtype=np.float32))

    np.testing.assert_allclose(probs, np.full(4, 0.25), rtol=1e-6)


def test_softmax_handles_large_negative_logits() -> None:
    service = bare_service()

    probs = service._softmax(np.array([-1000.0, -999.0], dtype=np.float32))

    assert np.isfinite(probs).all()


# ─────────────────────────────────────────────────────────────────────────────
# Degradation without a model
# ─────────────────────────────────────────────────────────────────────────────
def test_classify_without_a_model_asks_for_manual_input() -> None:
    """
    The absence of a classifier is an expected deployment state, not an error: the
    species is confirmed by the angler anyway.
    """
    result = bare_service().classify(bgr_image(224, 224))

    assert result == {"available": False, "requires_manual_input": True}


def test_available_is_false_without_a_session() -> None:
    assert bare_service().available is False


def test_classify_reports_unavailable_when_inference_raises() -> None:
    """A corrupt model must degrade, not propagate into the request."""

    class _ExplodingSession:
        """Session stand-in whose run() always fails."""

        @staticmethod
        def get_inputs() -> list:
            """Return one input descriptor."""

            class _Input:
                name = "input"

            return [_Input()]

        @staticmethod
        def run(*_args: object, **_kwargs: object) -> list:
            """Fail as a corrupt graph would."""
            raise RuntimeError("corrupt graph")

    service = bare_service()
    service.session = _ExplodingSession()
    service._available = True

    result = service.classify(bgr_image(224, 224))

    assert result["available"] is False
    assert result["requires_manual_input"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Prediction shaping
# ─────────────────────────────────────────────────────────────────────────────
class _StubSession:
    """ONNX session stand-in returning fixed logits."""

    def __init__(self, logits: np.ndarray) -> None:
        """Store the logits to return."""
        self._logits = logits

    def get_inputs(self) -> list:
        """Return one input descriptor named 'input'."""

        class _Input:
            name = "input"

        return [_Input()]

    def run(self, _outputs: object, _feed: dict) -> list:
        """Return the fixed logits as a batch of one."""
        return [self._logits.reshape(1, -1)]


def stubbed_service(logits: np.ndarray, labels: dict[int, str]) -> ClassifierService:
    """Build a service backed by a stub session."""
    service = bare_service()
    service.session = _StubSession(logits)
    service.labels = labels
    service._available = True
    return service


def test_predictions_are_ordered_by_descending_confidence() -> None:
    service = stubbed_service(
        np.array([0.1, 5.0, 2.0], dtype=np.float32),
        {0: "esox_lucius", 1: "cyprinus_carpio", 2: "perca_fluviatilis"},
    )

    result = service.classify(bgr_image(224, 224))

    slugs = [p["species_slug"] for p in result["predictions"]]
    confidences = [p["confidence"] for p in result["predictions"]]

    assert slugs[0] == "cyprinus_carpio"
    assert confidences == sorted(confidences, reverse=True)


def test_top_k_limits_the_number_of_predictions() -> None:
    service = stubbed_service(
        np.arange(10, dtype=np.float32), {i: f"species_{i}" for i in range(10)}
    )

    result = service.classify(bgr_image(224, 224), top_k=3)

    assert len(result["predictions"]) == 3


def test_confidences_are_probabilities() -> None:
    service = stubbed_service(
        np.array([1.0, 2.0, 3.0], dtype=np.float32), {0: "a", 1: "b", 2: "c"}
    )

    result = service.classify(bgr_image(224, 224))

    total = sum(p["confidence"] for p in result["predictions"])
    assert total == pytest.approx(1.0)
    assert all(0.0 <= p["confidence"] <= 1.0 for p in result["predictions"])


def test_an_unmapped_class_index_is_labelled_rather_than_dropped() -> None:
    """
    A labels file out of sync with the model must be visible, not silently produce
    a shorter prediction list.
    """
    service = stubbed_service(np.array([0.1, 9.0], dtype=np.float32), {0: "known"})

    result = service.classify(bgr_image(224, 224))

    assert result["predictions"][0]["species_slug"] == "unknown_1"


# ─────────────────────────────────────────────────────────────────────────────
# Non-forcing accessor
# ─────────────────────────────────────────────────────────────────────────────
def test_loaded_accessor_does_not_construct_the_service() -> None:
    """
    Health endpoints report model status; they must not trigger a model load on the
    first probe.
    """
    import app.services.classifier_service as module

    original = module._instance
    module._instance = None
    try:
        assert get_loaded_classifier_service() is None
    finally:
        module._instance = original
