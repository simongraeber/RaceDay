const MAX_SIDE = 1536

/**
 * Re-encode a picked photo as a resized JPEG so iPhone HEIC and 24-48 MP shots
 * stay small. Falls back to the original file if the browser can't decode it;
 * the server still accepts HEIC.
 */
export async function prepareUpload(file: File): Promise<File> {
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement("canvas")
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9))
    return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file
  } catch {
    return file
  }
}
