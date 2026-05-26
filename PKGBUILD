# Maintainer: yuri-cli maintainers <https://github.com/vlensys/yuri>
pkgname=yuri-cli
pkgver=0.1.0
pkgrel=1
pkgdesc="yuri straight in your terminal!"
arch=('any')
url="https://github.com/vlensys/yuri"
license=('MIT')
depends=('python' 'python-setuptools' 'mpv')
optdepends=(
  'fzf: interactive fuzzy selection menu'
  'kitty: GPU-accelerated image viewer for manga pages'
  'chafa: image viewer for manga pages (fallback)'
  'tiv: image viewer for manga pages (fallback)'
  'openssl: stream decryption required for AllAnime source'
)
source=("$pkgname-$pkgver.tar.gz::https://github.com/vlensys/yuri/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
  cd "yuri-$pkgver"
  python setup.py build
}

package() {
  cd "yuri-$pkgver"
  python setup.py install --root="$pkgdir" --optimize=1 --skip-build
}
