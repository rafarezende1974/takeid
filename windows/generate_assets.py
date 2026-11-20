"""Gera o icone do TakeID no runner (nada de binario no repo).

Icone proprio, relacionado a funcao — claquete roxa com imagem de
foto/video dentro — e nao o simbolo da DX Labs (regra dele: cada
app com seu icone, relacionado a funcao do app).
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
os.makedirs(OUT, exist_ok=True)


def build(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Corpo da claquete: quadrado roxo arredondado.
    d.rounded_rectangle([8, 52, 248, 248], radius=28, fill="#7B1FD0",
                        outline="#4A0E7A", width=4)
    # Tampa da claquete, inclinada, com listras claras.
    d.polygon([(14, 62), (238, 22), (248, 58), (24, 96)], fill="#A855F7",
              outline="#4A0E7A")
    for i in range(4):
        x0 = 52 + i * 52
        d.polygon([(x0, 54), (x0 + 26, 48), (x0 + 34, 74),
                   (x0 + 8, 80)], fill="#E9D5FF")
    # Listras da base.
    for i in range(3):
        x0 = 34 + i * 62
        d.polygon([(x0, 104), (x0 + 30, 104), (x0 + 12, 138),
                   (x0 - 18, 138)], fill="#E9D5FF")
    # "Foto" dentro da claquete: montanhas + sol.
    d.polygon([(48, 224), (118, 158), (168, 208), (196, 176),
               (224, 224)], fill="#E9D5FF")
    d.ellipse([168, 148, 200, 180], fill="#F0ABFC")
    return img


if __name__ == "__main__":
    icon = build(256)
    icon.save(os.path.join(OUT, "icon.png"))
    icon.save(os.path.join(OUT, "icon.ico"),
              sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print("assets/icon.png + assets/icon.ico gerados")
