"""Modal narrative dialogue plus a non-modal tutorial prompt."""

from __future__ import annotations

import pygame

from settings import COLOUR_MENU_BG,COLOUR_TEXT,COLOUR_TEXT_DIM,COLOUR_TOOLBAR_BORDER,COLOUR_TOOLBAR_BTN,COLOUR_TOOLBAR_BTN_HOVER,MAP_OFFSET_Y,WINDOW_HEIGHT,WINDOW_WIDTH,map_view_width


class ScenarioDialog:
    def __init__(self) -> None:
        self.font=pygame.font.SysFont("menlo",15)
        self.small=pygame.font.SysFont("menlo",12)
        self.text: str | None=None
        self.choices: tuple[str, ...]=()
        self.choice: int | None=None
        self._choice_rects: list[pygame.Rect]=[]
        self.dismissed=False
        self.objective_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def open(self) -> bool:return self.text is not None

    def show(self,text:str,choices:tuple[str,...]=()) -> None:
        self.text=text;self.choices=tuple(choices);self.choice=None;self.dismissed=False
    def close(self) -> None:self.text=None;self.choices=();self._choice_rects=[]

    def handle_event(self,event:pygame.event.Event) -> bool:
        if not self.open:return False
        if event.type==pygame.KEYDOWN and self.choices:
            if event.key in (pygame.K_1,pygame.K_KP1):self._dismiss(0)
            elif event.key in (pygame.K_2,pygame.K_KP2):self._dismiss(1)
        elif event.type==pygame.KEYDOWN and event.key in (pygame.K_RETURN,pygame.K_KP_ENTER,pygame.K_SPACE,pygame.K_ESCAPE):
            self._dismiss(None)
        elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            selected=next((i for i,r in enumerate(self._choice_rects) if r.collidepoint(event.pos)),None)
            if self.choices and selected is None:return True
            self._dismiss(selected)
        return True

    def _dismiss(self,choice:int|None) -> None:
        self.choice=choice;self.dismissed=True;self.close()

    @staticmethod
    def _wrap(font,text,width):
        lines=[];line=""
        for word in text.split():
            trial=f"{line} {word}".strip()
            if line and font.size(trial)[0]>width:lines.append(line);line=word
            else:line=trial
        if line:lines.append(line)
        return lines

    def draw(self,surface:pygame.Surface,prompt:str|None=None) -> None:
        self.objective_rect = pygame.Rect(0, 0, 0, 0)
        if prompt:
            label = self.small.render(prompt, True, COLOUR_TEXT)
            rect = label.get_rect(topright=(map_view_width() - 18, MAP_OFFSET_Y + 18)).inflate(24, 14)
            self.objective_rect = rect
            pygame.draw.rect(surface, (32, 37, 40), rect, border_radius=5)
            pygame.draw.rect(surface, COLOUR_TOOLBAR_BORDER, rect, 1, border_radius=5)
            surface.blit(label, label.get_rect(center=rect.center))
        if not self.open:return
        shade=pygame.Surface((WINDOW_WIDTH,WINDOW_HEIGHT),pygame.SRCALPHA);shade.fill((0,0,0,105));surface.blit(shade,(0,0))
        panel_h=250 if self.choices else 190
        panel=pygame.Rect((WINDOW_WIDTH-590)//2,(WINDOW_HEIGHT-panel_h)//2,590,panel_h)
        pygame.draw.rect(surface,COLOUR_MENU_BG,panel,border_radius=7);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,panel,2,border_radius=7)
        y=panel.y+28
        for line in self._wrap(self.font,self.text or "",panel.w-48):
            surface.blit(self.font.render(line,True,COLOUR_TEXT),(panel.x+24,y));y+=24
        self._choice_rects=[]
        if self.choices:
            cy=y+14
            for i,choice in enumerate(self.choices):
                button=pygame.Rect(panel.x+24,cy,panel.w-48,34);self._choice_rects.append(button)
                colour=COLOUR_TOOLBAR_BTN_HOVER if button.collidepoint(pygame.mouse.get_pos()) else COLOUR_TOOLBAR_BTN
                pygame.draw.rect(surface,colour,button,border_radius=4);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,button,1,border_radius=4)
                label=self.small.render(f"{i+1}. {choice}",True,COLOUR_TEXT);surface.blit(label,(button.x+10,button.y+9));cy+=42
            hint=self.small.render("Choose with click / 1 / 2",True,COLOUR_TEXT_DIM);surface.blit(hint,hint.get_rect(midbottom=(panel.centerx,panel.bottom-10)))
            return
        button=pygame.Rect(panel.centerx-65,panel.bottom-48,130,28)
        colour=COLOUR_TOOLBAR_BTN_HOVER if button.collidepoint(pygame.mouse.get_pos()) else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface,colour,button,border_radius=4);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,button,1,border_radius=4)
        label=self.small.render("Continue",True,COLOUR_TEXT);surface.blit(label,label.get_rect(center=button.center))
        hint=self.small.render("Enter / click",True,COLOUR_TEXT_DIM);surface.blit(hint,hint.get_rect(midtop=(panel.centerx,button.bottom+5)))
