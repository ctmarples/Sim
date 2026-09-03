"""Modal narrative dialogue plus a non-modal tutorial prompt."""

from __future__ import annotations

import pygame

from settings import COLOUR_MENU_BG,COLOUR_TEXT,COLOUR_TEXT_DIM,COLOUR_TOOLBAR_BORDER,COLOUR_TOOLBAR_BTN,COLOUR_TOOLBAR_BTN_HOVER,WINDOW_HEIGHT,WINDOW_WIDTH


class ScenarioDialog:
    def __init__(self) -> None:
        self.font=pygame.font.SysFont("menlo",15)
        self.small=pygame.font.SysFont("menlo",12)
        self.text: str | None=None
        self.dismissed=False

    @property
    def open(self) -> bool:return self.text is not None

    def show(self,text:str) -> None:self.text=text;self.dismissed=False
    def close(self) -> None:self.text=None

    def handle_event(self,event:pygame.event.Event) -> bool:
        if not self.open:return False
        if event.type==pygame.KEYDOWN and event.key in (pygame.K_RETURN,pygame.K_KP_ENTER,pygame.K_SPACE,pygame.K_ESCAPE):
            self.dismissed=True;self.close()
        elif event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            self.dismissed=True;self.close()
        return True

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
        if prompt:
            label=self.small.render(prompt,True,COLOUR_TEXT)
            rect=label.get_rect(midtop=(WINDOW_WIDTH//2,42)).inflate(24,14)
            pygame.draw.rect(surface,(32,37,40),rect,border_radius=5)
            pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,rect,1,border_radius=5)
            surface.blit(label,label.get_rect(center=rect.center))
        if not self.open:return
        shade=pygame.Surface((WINDOW_WIDTH,WINDOW_HEIGHT),pygame.SRCALPHA);shade.fill((0,0,0,105));surface.blit(shade,(0,0))
        panel=pygame.Rect((WINDOW_WIDTH-590)//2,(WINDOW_HEIGHT-190)//2,590,190)
        pygame.draw.rect(surface,COLOUR_MENU_BG,panel,border_radius=7);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,panel,2,border_radius=7)
        y=panel.y+28
        for line in self._wrap(self.font,self.text or "",panel.w-48):
            surface.blit(self.font.render(line,True,COLOUR_TEXT),(panel.x+24,y));y+=24
        button=pygame.Rect(panel.centerx-65,panel.bottom-48,130,28)
        colour=COLOUR_TOOLBAR_BTN_HOVER if button.collidepoint(pygame.mouse.get_pos()) else COLOUR_TOOLBAR_BTN
        pygame.draw.rect(surface,colour,button,border_radius=4);pygame.draw.rect(surface,COLOUR_TOOLBAR_BORDER,button,1,border_radius=4)
        label=self.small.render("Continue",True,COLOUR_TEXT);surface.blit(label,label.get_rect(center=button.center))
        hint=self.small.render("Enter / click",True,COLOUR_TEXT_DIM);surface.blit(hint,hint.get_rect(midtop=(panel.centerx,button.bottom+5)))
