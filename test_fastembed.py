from fastembed import TextEmbedding
from fastembed.common.model_description import PoolingType, ModelSource

TextEmbedding.add_custom_model(
    model="custom_e5_large",
    pooling=PoolingType.MEAN,
    normalization=True,
    sources=ModelSource(hf="intfloat/multilingual-e5-large"),
    dim=1024,
    model_file="model.onnx"
)

embedder = TextEmbedding(model_name="custom_e5_large")
res = list(embedder.embed(["hello"]))
print("Dim:", len(res[0]))
