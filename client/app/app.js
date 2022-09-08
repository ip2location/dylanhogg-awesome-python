var version = "v0.0.7";

function getUrlParams() {
    // Ref: https://stackoverflow.com/questions/4656843/get-querystring-from-url-using-jquery/4656873#4656873
    var vars = [], hash;
    var hashes = window.location.href.slice(window.location.href.indexOf('?') + 1).split('&');
    for(var i = 0; i < hashes.length; i++) {
        hash = hashes[i].split('=');
        vars.push(hash[0]);
        vars[hash[0]] = hash[1];
    }
    return vars;
}

function getUrlQuery() {
    try {
        var params = getUrlParams();
        if ("q" in params) { return decodeURI(params["q"]); } else { return ""; }
    } catch(err) {
        return "";
    }
}

$(document).ready( function () {
    var ajax_url = './github_data.min.json';
    // var ajax_url = 'https://crazy-awesome-python-api.infocruncher.com/github_data.min.json';
    if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
        // Use local testing json data
        ajax_url = '/github_data.json';
    }

    var initialSearchTerm = getUrlQuery();
    $("#table").DataTable( {
        ajax: {
            url: ajax_url,
            dataSrc: 'data'
        },
        responsive: true,
        order: [[ 1, "desc" ]],
        paging: true,
        lengthChange: true,
        lengthMenu: [[10, 50, 100, -1], [10, 50, 100, "All"]],
        pageLength: 10,
        search: {
           search: initialSearchTerm
        },
        // dom: 'lfrtip',  // Default. https://datatables.net/reference/option/dom
        dom: 'frtilp',
        columns: [
//          { data: "_requirements_localurls", title: "Requirements",
//            render: function(data, type, row, meta) {
//                if (data.length > 0) {
//                    var links = "";
//                    for (var i=0; i<data.length; i++) {
//                        var filename = data[i];
//                        var url = "/data/" + filename + "";
//                        var title = "unknown";
//                        if (filename.indexOf("requirements.txt") > 0) {
//                            title = "requirements.txt";
//                        } else if (filename.indexOf("setup.py") > 0) {
//                            title = "setup.py";
//                        } else if (filename.indexOf("pyproject.toml") > 0) {
//                            title = "pyproject.toml";
//                        }
//                        links = links + "<a class='modal-ajax' href='#' data-localurl='"+url+"' data-ext='' data-title='"+title+"' data-replace-lf='true'>"+title+"</a><br />";
//                    }
//                    return links;
//                } else {
//                    return "";
//                }
//
//            }
//          },
          { data: null,
            title: "Project",
            render: function(data, type, row, meta) {
                var repoUrl = "<a href='" + row.githuburl + "' target='_blank'>" + "<img src='img/repo.png' class='github-img'></img></a>&nbsp;<a href='" + row.githuburl + "'>" + row._reponame.toLowerCase() + "</a>";
                var orgUrl = "<br /><a href='https://github.com/" + row._organization + "' target='_blank'>" + "<img src='img/org.png' class='github-img'></img></a>&nbsp;<a href='https://github.com/" + row._organization + "'>" + row._organization.toLowerCase() + "</a>";
                var homepageUrl = "";
                try { homepageUrl = "<br /><a href='" + row._homepage + "' target='_blank'><img src='img/web.png' class='web-img'></img></a>&nbsp;<a href='" + row._homepage + "'>" + new URL(row._homepage).hostname + "</a>"; } catch { }
                return repoUrl + orgUrl + homepageUrl;
             }
           },
           { data: "_stars_per_week", title: "Stars<br />per&nbsp;week",
            render: function(data, type, row, meta) { return data > 10 ? data.toFixed(0) : data.toFixed(1); }
          },
          { data: "_stars", title: "Stars&nbsp;<img src='img/star.png' class='github-img' />", className: "text-nowrap", render: $.fn.dataTable.render.number(',', '.', 0) },
           { data: "_description", title: "Description",
             render: function(data, type, row, meta) { return "<div class='text-wrap description-column'>" + data + "</div>"; }
           },
          { data: "_forks", title: "Forks&nbsp;<img src='img/fork.png' class='github-img' />", className: "text-nowrap", render: $.fn.dataTable.render.number(',', '.', 0) },
          { data: "_updated_at", title: "Updated&nbsp;<img src='img/clock.png' class='github-img' />",
            className: "text-nowrap",
            render: function(data, type, row, meta) { return new Date(data).toISOString().split('T')[0]; }
          },
          { data: "_created_at", title: "Created&nbsp;<img src='img/clock.png' class='github-img' />",
            className: "text-nowrap",
            render: function(data, type, row, meta) { return new Date(data).toISOString().split('T')[0]; }
          },
          { data: "_age_weeks", title: "Age in&nbsp;weeks",
            render: function(data, type, row, meta) { return data.toFixed(0); }
          },
          { data: "category", title: "Category" },
          { data: "_topics", title: "Tags",
            render: function(data, type, row, meta) { return data.slice(0, 4).join(", "); }
          },
          { data: "_readme_localurl", title: "Docs",
            orderable: false,
            render: function(data, type, row, meta) {
                if (data.length > 0) {
                    var url = "/data/" + data + "";
                    return "<img src='img/github.png' alt='info' title='View install and GitHub info' class='modal-ajax info-img' href='#' data-localurl='"+url+"' data-ext='.html' data-title='' data-replace-lf='false'></img>";
                } else {
                    return "";
                }
            }
          },
        ],
    });

    $('#table').on('click', '.modal-ajax', function(e) {
        var localurl = $(this).data('localurl') + $(this).data('ext');
        e.preventDefault();

        $.ajax({
           type: "GET",
           url: localurl,
           title: $(this).data('title'),
           replace_lf: $(this).data('replace-lf'),
           success: function(content)
           {
                if (this.replace_lf) {
                    content = content.replace(/\n/g, '<br />');
                }
                var html = "<div class='modal'>";
                if (this.title.length > 0) {
                    html = html + "<b>" + this.title + "</b><br /><br />";
                }
                html = html + content + "</div>";
                $(html).appendTo("#container").modal();
           },
           error: function(html)
           {
                console.log("ERROR getting localurl: " + localurl);
           },
        });

        return false;
    });
});



