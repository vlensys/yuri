pkgname=yuri
pkgver=0.1.0
pkgrel=1
pkgdesc="yuri straight in your terminal!"
arch=('any')
url="https://github.com/vlensys/yuri"
license=('MIT')
depends=('python' 'python-setuptools' 'mpv')
optdepends=(
  'fzf: interactive fuzzy selection menu'
  'openssl: stream decryption for AllAnime'
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
