"""Presentation helpers for symmetric, normal-approximation fit intervals."""
from decimal import Decimal, ROUND_DOWN, localcontext
import csv
from math import hypot, isfinite, log10, floor


STANDARD_ERROR_SUFFIX = '_standard_error'
STANDARD_ERROR_DESCRIPTION = 'One standard error (approximately 68% symmetric interval)'


def amplitude_standard_error(*, free, std, twin=None, active=True):
    """A constrained or unavailable amplitude has no estimated uncertainty."""
    if not active or not free or twin is not None or std is None:
        return float('nan')
    try:
        value = float(std)
    except (ValueError, TypeError):
        return float('nan')
    return value if isfinite(value) and value > 0 else float('nan')


def saved_amplitude_standard_errors(components):
    """Read saved amplitude errors, including snapshots predating std fields."""
    return {
        component['name']: amplitude_standard_error(
            free=parameter.get('free', False), std=parameter.get('std'),
            twin=parameter.get('twin_component'), active=component.get('active', True))
        for component in components
        for parameter in component.get('parameters', [])
        if parameter['name'] == 'A'
    }


def write_fitted_intensity_csv(path, lines, values, standard_errors, *, spectrum_header='Spectrum'):
    """Write unrounded values with adjacent one-standard-error columns."""
    with open(path, 'w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([spectrum_header] + [name for line in lines for name in (line, line + STANDARD_ERROR_SUFFIX)])
        for spectrum, intensities in values.items():
            row = [spectrum]
            errors = standard_errors.get(spectrum, {})
            for line in lines:
                for value in (intensities.get(line, float('nan')), errors.get(line, float('nan'))):
                    row.append(float(value) if isfinite(value) else 'NaN')
            writer.writerow(row)


def normalized_half_width(value, half_width, reference, reference_half_width, *, same_line=False):
    """Delta-method ratio interval, neglecting unavailable cross-covariances."""
    if not all(isfinite(v) for v in (value, half_width, reference, reference_half_width)) or reference == 0:
        return float('nan')
    if same_line:
        return 0.0
    return hypot(half_width / reference, (value / reference) * (reference_half_width / reference))


def format_with_uncertainty(value, half_width):
    """Use two significant uncertainty digits; truncate at the same place.

    Parentheses contain the uncertainty in the last displayed digits. Large
    uncertainty places use an explicit exponent to keep that meaning unambiguous.
    """
    if not isfinite(value):
        return 'NaN'
    if not isfinite(half_width) or half_width < 0:
        return f'{value:.6g}(NaN)'
    if half_width == 0:
        return f'{value:.6g}(00)'
    uncertainty_place = floor(log10(half_width)) - 1
    exponent = 0
    if uncertainty_place > 0 or uncertainty_place < -6:
        exponent = floor(log10(abs(value))) if value else floor(log10(half_width))
        exponent = max(exponent, uncertainty_place)
    with localcontext() as context:
        context.prec = max(40, len(str(value)) + abs(uncertainty_place) + abs(exponent) + 5)
        quantum = Decimal(1).scaleb(uncertainty_place)
        uncertainty = Decimal(str(half_width)).quantize(quantum, rounding=ROUND_DOWN)
        truncated = Decimal(str(value)).quantize(quantum, rounding=ROUND_DOWN)
        digits = int(uncertainty / quantum)
        decimals = max(0, exponent - uncertainty_place)
        text = f'{truncated.scaleb(-exponent):.{decimals}f}({digits:02d})'
    return text + (f'e{exponent:+d}' if exponent else '')
