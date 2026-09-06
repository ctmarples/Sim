"""Wrapped quest checklist rows shared by the journal and viewport card."""
import pygame


def wrap(font, text, width):
    lines, line = [], ''
    for word in text.split():
        trial = f'{line} {word}'.strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def _item_lines(font, item, width, *, indent=False):
    """Yield (text, kind) rows for one objective, optionally indented."""
    lines = []
    label_width = width - (40 if indent else 22)
    tip_width = width - (52 if indent else 34)
    for index, text in enumerate(wrap(font, item['label'], label_width)):
        kind = item['completed'] if index == 0 else None
        if indent and index == 0:
            kind = ('child', item['completed'])
        elif indent:
            kind = 'child_wrap'
        lines.append((text, kind))
    tip = item.get('tip', '')
    if tip and not item.get('completed'):
        for text in wrap(font, tip, tip_width):
            lines.append((text, 'child_tip' if indent else 'tip'))
    return lines


def detail_lines(font, quest, width, *, explanation=False):
    lines = []
    for item in quest.get('objectives', []):
        lines.extend(_item_lines(font, item, width))
        for child in item.get('children', []):
            lines.extend(_item_lines(font, child, width, indent=True))
        lines.append(('', 'gap'))
    if lines and lines[-1][1] == 'gap':
        lines.pop()
    for text in (quest.get('note', ''),
                 quest.get('explanation', '') if explanation else ''):
        if text:
            lines.append(('', 'gap'))
            lines.extend((line, None) for line in wrap(font, text, width - 22))
    return lines


def draw_line(surface, font, text, checked, x, y, colour):
    if checked == 'gap':
        return
    if checked in ('tip', 'child_tip'):
        surface.blit(font.render(text, True, colour), (x + (48 if checked == 'child_tip' else 34), y))
        return
    if checked == 'child_wrap':
        surface.blit(font.render(text, True, colour), (x + 40, y))
        return
    indent = 0
    done = checked
    if isinstance(checked, tuple) and checked and checked[0] == 'child':
        indent = 18
        done = checked[1]
    if done is not None:
        box = pygame.Rect(x + 1 + indent, y + max(1, (font.get_height()-11)//2), 11, 11)
        pygame.draw.rect(surface, colour, box, 1)
        if done:
            pygame.draw.lines(surface, colour, False,
                              [(box.x+2, box.y+5), (box.x+5, box.y+8), (box.x+9, box.y+2)], 2)
        surface.blit(font.render(text, True, colour), (x + 20 + indent, y))
        return
    surface.blit(font.render(text, True, colour), (x + 20 + indent, y))
