import random
import sys

import pygame

# Initialize Pygame
pygame.init()
pygame.font.init()

# Game Constants
WIDTH, HEIGHT = 800, 600
GRID_SIZE = 20
GRID_WIDTH = WIDTH // GRID_SIZE
GRID_HEIGHT = HEIGHT // GRID_SIZE
FPS = 12

# Colors
BACKGROUND = (15, 23, 42)     # Dark slate blue
SNAKE_HEAD = (16, 185, 129)   # Emerald green
SNAKE_BODY = (52, 211, 153)   # Mint green
FOOD_COLOR = (244, 63, 94)    # Rose red
TEXT_COLOR = (248, 250, 252)  # White
GRID_LINE = (30, 41, 59)      # Subtle grid line

# Setup Screen
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Nexus Snake Game")
clock = pygame.time.Clock()
font = pygame.font.SysFont("Helvetica", 28, bold=True)
large_font = pygame.font.SysFont("Helvetica", 48, bold=True)

class SnakeGame:
    def __init__(self):
        self.reset()

    def reset(self):
        self.snake = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.score = 0
        self.game_over = False
        self._spawn_food()

    def _spawn_food(self):
        while True:
            self.food = (
                random.randint(0, GRID_WIDTH - 1),
                random.randint(0, GRID_HEIGHT - 1)
            )
            if self.food not in self.snake:
                break

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_r):
                        self.reset()
                else:
                    if event.key in (pygame.K_UP, pygame.K_w) and self.direction != (0, 1):
                        self.next_direction = (0, -1)
                    elif event.key in (pygame.K_DOWN, pygame.K_s) and self.direction != (0, -1):
                        self.next_direction = (0, 1)
                    elif event.key in (pygame.K_LEFT, pygame.K_a) and self.direction != (1, 0):
                        self.next_direction = (-1, 0)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d) and self.direction != (1, 0):
                        self.next_direction = (1, 0)

    def update(self):
        if self.game_over:
            return

        self.direction = self.next_direction
        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)

        # Check Wall Collision
        if not (0 <= new_head[0] < GRID_WIDTH and 0 <= new_head[1] < GRID_HEIGHT):
            self.game_over = True
            return

        # Check Self Collision
        if new_head in self.snake:
            self.game_over = True
            return

        self.snake.insert(0, new_head)

        # Check Food Collision
        if new_head == self.food:
            self.score += 10
            self._spawn_food()
        else:
            self.snake.pop()

    def draw(self):
        screen.fill(BACKGROUND)

        # Draw Grid Background Lines
        for x in range(0, WIDTH, GRID_SIZE):
            pygame.draw.line(screen, GRID_LINE, (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, GRID_SIZE):
            pygame.draw.line(screen, GRID_LINE, (0, y), (WIDTH, y))

        # Draw Food
        fx, fy = self.food
        food_rect = pygame.Rect(fx * GRID_SIZE + 2, fy * GRID_SIZE + 2, GRID_SIZE - 4, GRID_SIZE - 4)
        pygame.draw.ellipse(screen, FOOD_COLOR, food_rect)

        # Draw Snake
        for idx, (sx, sy) in enumerate(self.snake):
            rect = pygame.Rect(sx * GRID_SIZE + 1, sy * GRID_SIZE + 1, GRID_SIZE - 2, GRID_SIZE - 2)
            color = SNAKE_HEAD if idx == 0 else SNAKE_BODY
            pygame.draw.rect(screen, color, rect, border_radius=4)

        # Draw Score HUD
        score_surface = font.render(f"Score: {self.score}", True, TEXT_COLOR)
        screen.blit(score_surface, (15, 15))

        # Draw Game Over Overlay
        if self.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((15, 23, 42, 200))
            screen.blit(overlay, (0, 0))

            title_surf = large_font.render("GAME OVER", True, (244, 63, 94))
            score_surf = font.render(f"Final Score: {self.score}", True, TEXT_COLOR)
            sub_surf = font.render("Press SPACE or R to Restart", True, (148, 163, 184))

            screen.blit(title_surf, title_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 50)))
            screen.blit(score_surf, score_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 10)))
            screen.blit(sub_surf, sub_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 60)))

        pygame.display.flip()

    def run(self):
        while True:
            self.handle_input()
            self.update()
            self.draw()
            clock.tick(FPS)

if __name__ == "__main__":
    game = SnakeGame()
    game.run()
